"""Generate affiliate links for Amazon (direct, tag-based) and Rakuten (Rakuten Web Service).

2026-07-21: もしもアフィリエイトのサイト登録が削除されたため、もしも経由のURLラップをやめ、
Amazonは直接タグ付きリンク、楽天は楽天ウェブサービス「楽天市場商品検索API」を直接叩いて
アフィリエイトURLを取得する方式に切り替えた（manga-calプロジェクトの楽天ブックスAPI連携と
同じ認証方式: RAKUTEN_APP_ID + RAKUTEN_ACCESS_KEY + RAKUTEN_AFFILIATE_ID）。

楽天APIは実際のHTTPリクエストが発生する(レート制限あり、目安1req/秒)ため、既にDBに保存済みの
URLがある商品については呼び出し側(run.py)で再取得をスキップすること。
"""
import os
import time
import urllib.parse

import httpx

RAKUTEN_SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
RAKUTEN_MIN_INTERVAL_SEC = 1.1

# 楽天ウェブサービスのアプリ登録をドメイン制限した「Webアプリケーション」タイプで行った場合、
# サーバーサイドからの素のリクエストは拒否されることがある(manga-calプロジェクトで実機確認済み)。
# 登録済みドメインのReferer/Originを付与して回避する。
REGISTERED_ORIGIN = "https://gacha-calendar-20p.pages.dev"
BROWSER_LIKE_HEADERS = {
    "Referer": f"{REGISTERED_ORIGIN}/",
    "Origin": REGISTERED_ORIGIN,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

_last_rakuten_call = 0.0


def _amazon_tag() -> str:
    return os.environ.get("AMAZON_AFFILIATE_TAG", "")


def _rakuten_creds() -> tuple[str, str, str]:
    return (
        os.environ.get("RAKUTEN_APP_ID", ""),
        os.environ.get("RAKUTEN_ACCESS_KEY", ""),
        os.environ.get("RAKUTEN_AFFILIATE_ID", ""),
    )


def amazon_search_url(keyword: str) -> str:
    query = urllib.parse.quote(keyword)
    url = f"https://www.amazon.co.jp/s?k={query}"
    tag = _amazon_tag()
    if tag:
        url += f"&tag={tag}"
    return url


def _rakuten_plain_search_url(keyword: str) -> str:
    """API呼び出しができない/失敗した場合の非アフィリエイトフォールバック。"""
    encoded = urllib.parse.quote(keyword)
    return f"https://search.rakuten.co.jp/search/mall/{encoded}/"


def _rakuten_api_search(keyword: str) -> str | None:
    """楽天市場商品検索APIを1回呼び出す。ヒットすればaffiliateUrl(無ければitemUrl)を返す。
    ノーヒット/APIエラー時はNoneを返す(呼び出し側で別キーワードでの再試行に使うため)。"""
    app_id, access_key, affiliate_id = _rakuten_creds()

    global _last_rakuten_call
    elapsed = time.monotonic() - _last_rakuten_call
    if elapsed < RAKUTEN_MIN_INTERVAL_SEC:
        time.sleep(RAKUTEN_MIN_INTERVAL_SEC - elapsed)

    params = {
        "applicationId": app_id,
        "accessKey": access_key,
        "keyword": keyword,
        "hits": 1,
        "sort": "standard",
    }
    if affiliate_id:
        params["affiliateId"] = affiliate_id

    try:
        resp = httpx.get(RAKUTEN_SEARCH_URL, params=params, headers=BROWSER_LIKE_HEADERS, timeout=10)
        _last_rakuten_call = time.monotonic()
        resp.raise_for_status()
        data = resp.json()
        items = data.get("Items") or []
        if not items:
            return None
        item = items[0].get("Item", {})
        return item.get("affiliateUrl") or item.get("itemUrl") or None
    except Exception:
        _last_rakuten_call = time.monotonic()
        return None


def rakuten_search_url(clean_name: str, maker: str | None = None) -> str:
    """楽天市場商品検索APIで商品を検索し、最上位商品のアフィリエイトURLを返す。

    実データで確認した重要な挙動: メーカー名を検索語に含めると逆にヒットしなくなるケースが多い
    (例: 「タカラトミーアーツ JOGUMAN もふもふポーシェット」は0件だが、
    「JOGUMAN もふもふポーシェット」単体だと10件ヒットする。楽天の出品者はメーカーの正式社名を
    商品名に含めないことが多いため)。そのため、まず商品名単体で検索し、ヒットしなければ
    メーカー名付きで再試行する(逆に商品名単体だと一般的すぎる場合に効くことがある)。
    どちらもヒットしない/認証情報未設定/APIエラー時は非アフィリエイトの検索URLにフォールバックする
    (リンク自体は常に返す。呼び出し側でNoneを気にしなくてよいようにするため)。
    """
    app_id, access_key, _ = _rakuten_creds()
    combined = f"{maker} {clean_name}".strip() if maker else clean_name
    if not app_id or not access_key:
        return _rakuten_plain_search_url(combined)

    url = _rakuten_api_search(clean_name)
    if not url and maker:
        url = _rakuten_api_search(combined)
    return url or _rakuten_plain_search_url(combined)


def generate_links(clean_name: str, maker: str | None = None, existing_rakuten_url: str | None = None) -> dict[str, str]:
    """existing_rakuten_url: DBに既に保存済みの楽天URLがあれば渡す。API再呼び出しをスキップする
    (呼び出し側=run.pyが日次パイプラインで全件を毎回舐めるため、既存商品への再検索を避けてレート制限・
    実行時間を抑える)。"""
    keyword = f"{maker} {clean_name}".strip() if maker else clean_name
    rakuten = existing_rakuten_url or rakuten_search_url(clean_name, maker)
    return {
        "amazon": amazon_search_url(keyword),
        "rakuten": rakuten,
    }
