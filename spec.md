# ガチャガチャ・食玩 発売カレンダー速報システム — spec.md

最終更新: 2026-06-17
リポジトリ: https://github.com/xxvicexx-cyber/gacha-calendar
実装環境: Python 3.11+ / GitHub Actions / Astro SSG（デプロイ先未定）

---

## 0. プロジェクト概要

ガチャガチャ（カプセルトイ）の発売予定情報を自動収集し、

1. **X（旧Twitter）** でアフィリエイトリンク付き速報を自動投稿
2. **Discord** で速報配信 → コミュニティへ誘客
3. **Webサイト**（Astro SSG）で月別発売カレンダーとして公開（デプロイ先は追って設定）
4. **アフィリエイト**（Amazon / 楽天）で収益化

する仕組みを構築する。

---

## 1. 設計上の制約

### 1.1 X投稿は Playwright 自動投稿（コストゼロ）
- X API を使わず **Playwright ブラウザ自動投稿** で行う。
- クッキーファイル（`data/x_cookies.json`）または GitHub Secret（`X_COOKIES`）に保存したセッションで認証。
- 投稿間隔: **60〜180秒ランダム**、1回の実行で最大5件。
- 1投稿 **270文字以内**（X制限280の安全マージン）。URLはX仕様の23文字換算で計算。
- 文字数超過時の省略優先度: Discord招待 → ハッシュタグ短縮 → アフィリエイトURL。

### 1.2 法令・規約コンプライアンス
- スクレイピング前に robots.txt を確認（`scrapers/base.py` で自動チェック）。
- あミューズは公開ページの範囲のみ取得（商品名・コード・発売月・価格・メーカー）。
- アフィリエイトリンクを含む投稿には **「PR」表記**（Amazonリンクに「PR」を明記）。
- メーカー・あミューズの画像は**再ホストしない**（参照のみ）。

---

## 2. データソース

### 2.1 あミューズ（主力・唯一の実装済みソース）

URL: `https://www.a-muzu.com/`  
robots.txt 確認済み: `/category/` 以下はクロール許可。

| カテゴリ | URL パターン | 内容 |
|---|---|---|
| 月別入荷予定（核） | `/category/SCHEDULE_YYYYMM/` | 最大5ヶ月先まで巡回 |
| 発売日変更・中止 | `/category/SCHEDULE_CHANGE/` | 延期・中止の速報 |

**ページネーション**: `?SEARCH_MAX_ROW_LIST=60&item_list_mode=1&sort_order=1&request=page&next_page=N`  
（`/category/` パスなので robots.txt の `/item_list.html?...` 禁止とは無関係）

**HTML構造**（実測確認済み）:
```
a.p-schedule-item
  ├─ .p-schedule-item__arrival-date      発売日（例: "2026/07/06"）
  ├─ .p-schedule-item__arrival-type img  価格gif（例: "400yen.gif" → 400円）
  ├─ .p-schedule-item__product-image img 商品画像 URL
  ├─ .p-schedule-item__product-title     商品名（全タグ付き原文）
  └─ .p-schedule-item__product-code      "商品コード：C68227"
```

**取得実績**: 6月 454件、7月 585件（2026-06-17時点）

---

## 3. システム構成

```
[あミューズ scraper]
  ↓ httpx + BeautifulSoup4
[Normalizer] → maker / release_month / lot_qty / ip_tag / flags 抽出
  ↓
[SQLite DB]
  ├─ products（主キー: source_code）
  ├─ release_changes（発売日変更履歴）
  ├─ affiliate_links（Amazon/楽天リンク）
  └─ post_log（重複配信防止）
  ↓
  ├─ [Discord Webhook]  embed形式速報（アフィリエイトリンクのみ、あミューズ直リンクなし）
  ├─ [X Poster]         Playwright自動投稿（アフィリエイトリンク＋Discord誘客）
  └─ [Site Data]        site/src/data/*.json → Astro SSG ビルド用
```

---

## 4. ディレクトリ構成

```
gacha-calendar/
├─ spec.md
├─ run.py                    # メインパイプライン
├─ requirements.txt
├─ .env                      # ローカル用（git管理外）
├─ .env.example
├─ scrapers/
│  ├─ base.py                # httpx + robots.txt確認 + レート制御（1〜2.5秒）
│  ├─ amuzu.py               # SCHEDULE_YYYYMM 月別巡回（全ページ）
│  └─ amuzu_changes.py       # SCHEDULE_CHANGE ページ
├─ pipeline/
│  ├─ normalize.py           # 商品名パース・NFKC正規化
│  └─ affiliate.py           # Amazon/楽天 検索リンク生成
├─ store/
│  ├─ schema.sql
│  └─ db.py                  # SQLite WAL, upsert, 差分記録
├─ distribute/
│  ├─ discord.py             # Discord Webhook（embed、アフィリエイトリンクのみ）
│  └─x_poster.py             # Playwright投稿（270文字制御、Discord誘客URL付き）
├─ site/                     # Astro SSG（未デプロイ）
│  ├─ astro.config.mjs
│  ├─ package.json
│  └─ src/
│     ├─ data/               # run.py が生成する JSON（git管理外）
│     ├─ layouts/Layout.astro
│     └─ pages/
│        ├─ index.astro      # 月一覧
│        ├─ [month].astro    # 月別カレンダー
│        └─ about.astro      # PR表記・免責
└─ .github/workflows/
   └─ daily.yml              # GitHub Actions cron（9:00/19:00 JST）
```

---

## 5. データモデル

```sql
-- 主テーブル
products (
  source_code   TEXT UNIQUE,   -- あミューズ商品コード（例: C68227）主キー
  name          TEXT,          -- 原文商品名
  clean_name    TEXT,          -- 【】《》※ 除去後の表示名
  maker         TEXT,          -- 半角カナ→全角変換済み
  play_price    INTEGER,       -- 1回あたり消費者価格（200/300/400/500円）
  release_month TEXT,          -- 'YYYY-MM'（延期上書き適用後）
  release_date  DATE,          -- 日まで判明した場合（例: '2026-07-06'）
  release_text  TEXT,          -- "※7月発売へ延期※" 等の原文
  is_reprint    INTEGER,       -- 《再販》フラグ
  overseas_ng   INTEGER,       -- 【予約海外NG】フラグ
  lot_qty       INTEGER,       -- 入数（卸ロット）
  ip_tag        TEXT,          -- 版権タグ（サンリオ/ポケモン等）
  image_url     TEXT,          -- 参照のみ（再ホスト不可）
  detail_url    TEXT,          -- あミューズ詳細URL（外部公開しない）
  first_seen_at TIMESTAMP,     -- 速報トリガー判定用
  updated_at    TIMESTAMP
)

-- 変更履歴（延期・中止の速報に使用）
release_changes (source_code, changed_at, field, old_value, new_value)

-- アフィリエイトリンク
affiliate_links (product_id, asp, url)   -- asp: 'amazon' | 'rakuten'

-- 二重配信防止
post_log (product_id, channel)           -- channel: 'discord' | 'x'
```

---

## 6. 商品名の正規化仕様

入力例:
```
※7月発売へ延期※【6月先行受注】【二次予約】《再販》モンチッチマスコットキーチェーン2（30個入り）【SO-TA】【予約海外NG】カプセルトイ
```

出力:
| フィールド | 値 |
|---|---|
| `clean_name` | `モンチッチマスコットキーチェーン2` |
| `release_month` | `2026-07`（※延期先を採用） |
| `release_text` | `※7月発売へ延期※` |
| `maker` | `SO-TA` |
| `lot_qty` | `30` |
| `is_reprint` | `True` |
| `overseas_ng` | `True` |
| `ip_tag` | `モンチッチ` |

**release_month 決定ロジック（優先順）**:
1. `※N月発売へ延期※` → N月（延期後を採用）
2. `【N月発売】` タグ
3. 巡回元カテゴリURL（`SCHEDULE_202607` → `2026-07`）

**メーカー判定**: 末尾の`【...】`タグのうち、月・予約・海外NG等のキーワードを除いたもの。半角カナはNFKC変換（例: `【ﾋﾟｰﾅｯﾂｸﾗﾌﾞ】` → `ピーナッツクラブ`）。

---

## 7. X投稿フォーマット

```
【再販】🎰 {商品名（最大30文字）}
📅 {発売日}　💴 {価格}円
🛒 Amazon（PR）
https://af.moshimo.com/...
#ガチャガチャ #カプセルトイ #{IPタグ}
💬 Discord
https://discord.gg/mNSWwmne
```

- **文字数上限**: 270字（X仕様280の安全マージン）
- **URL**: X仕様で23字換算。実測 137〜143字程度
- **省略優先度**: Discord招待 → ハッシュタグ短縮 → アフィリエイト（最後まで残す）
- **投稿間隔**: 60〜180秒ランダム
- **1実行あたり最大投稿数**: 5件

---

## 8. Discord 速報フォーマット

Discord embed（タイトルはリンクなし＝あミューズへの直リンクを排除）:

```
🆕 新着：モンチッチマスコットキーチェーン2
─────────────────────
メーカー: SO-TA
発売日: 2026-07-06
価格: 400円
《再販》 / 【予約海外NG】

🛒 Amazonで探す（PR）  ← アフィリエイトリンク
🛒 楽天で探す（PR）    ← アフィリエイトリンク
```

- タイトルをクリックしても外部サイトには飛ばない設計
- 変更速報の場合は `⚠️ 変更：...` タイトルで変更項目を明示

---

## 9. アフィリエイト

| ASP | 対象 | 設定方法 |
|---|---|---|
| もしもアフィリエイト | Amazon / 楽天まとめて | `MOSHIMO_AFFILIATE_ID` 環境変数 |
| Amazonアソシエイト | Amazon単体 | `AMAZON_AFFILIATE_TAG` 環境変数 |

リンク形式: 商品名（maker + clean_name）でキーワード検索URL → もしもURLでラップ。

---

## 10. GitHub Actions（自動実行）

スケジュール: 毎日 **9:00 JST / 19:00 JST** の2回（UTC 0:00 / 10:00）

実行ステップ:
1. Python 依存パッケージ install
2. SQLite DB をキャッシュから復元
3. `python run.py` 実行
   - あミューズ scraping（5ヶ月分）
   - DB upsert + 差分検知
   - Discord Webhook 速報
   - X Playwright 自動投稿（`X_COOKIES` Secret がある場合のみ）
4. 失敗時: Discord に `⚠️ GitHub Actions failed!` 通知

### GitHub Secrets 一覧

| Secret名 | 用途 | 状態 |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Discord速報 | ✅ 設定済み |
| `DISCORD_INVITE_URL` | X投稿の招待リンク | 要設定 |
| `X_COOKIES` | X Playwright認証（base64 JSON） | クッキー準備待ち |
| `AMAZON_AFFILIATE_TAG` | Amazon ASP | 任意 |
| `MOSHIMO_AFFILIATE_ID` | もしもアフィリエイト | 任意 |

---

## 11. 環境変数（.env）

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_INVITE_URL=https://discord.gg/mNSWwmne
AMAZON_AFFILIATE_TAG=yourtag-22
MOSHIMO_AFFILIATE_ID=
X_COOKIE_FILE=data/x_cookies.json   # ローカル実行時のクッキーパス
```

---

## 12. ローカル実行

```bash
# 初回セットアップ
pip install -r requirements.txt

# フルパイプライン実行
python run.py

# オプション
python run.py --skip-scrape     # スクレイプをスキップ（通知・サイトデータのみ）
python run.py --skip-notify     # Discord通知をスキップ
python run.py --skip-x          # X投稿をスキップ
python run.py --skip-site       # サイトデータ生成をスキップ
python run.py --months-ahead 3  # 先読み月数（デフォルト5）

# X クッキーのセットアップ
python -c "from distribute.x_poster import save_cookies_from_file; save_cookies_from_file('export_cookies.json')"

# サイトビルド（ローカル確認用）
cd site && npm install && npm run build && npm run preview
```

---

## 13. 実装状況

### 完了
- [x] あミューズ scraper（SCHEDULE_YYYYMM / SCHEDULE_CHANGE）
- [x] SQLite DB（upsert・変更履歴・重複配信防止）
- [x] 商品名正規化パイプライン
- [x] もしもアフィリエイト リンク生成
- [x] Discord Webhook 速報（アフィリエイトリンクのみ）
- [x] X Playwright 自動投稿（270字制御・Discord誘客）
- [x] Astro SSG サイト（月別カレンダー・about ページ）
- [x] GitHub Actions 日次 cron

### 未設定（次のステップ）
- [ ] GitHub Secret: `DISCORD_INVITE_URL` 登録
- [ ] X クッキーファイル取得 → `X_COOKIES` Secret 登録
- [ ] Astro サイトのデプロイ先決定（Vercel 等）

### Phase 2 以降（未実装）
- [ ] メーカー一次ソース追加（バンダイ公式・T-ARTS 等）
- [ ] .ics カレンダーファイル生成
- [ ] IP別ページ（ポケモン・サンリオ等）でSEO強化
- [ ] プレミアム先行通知（Discord有料ロール）
- [ ] B2Bデータ提供 / 物販連携
