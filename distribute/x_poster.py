"""X（旧Twitter）へのPlaywright自動投稿。

クッキー認証方式（boat-ai / bonbon-monitor と同じ方式）。
クッキーは JSON ファイルまたは X_COOKIES 環境変数（base64 JSON）から読む。

使い方:
  1. ブラウザで X にログインし Cookie Exporter 等でクッキーを export_cookies.json に保存
  2. python -c "from distribute.x_poster import save_cookies_from_file; save_cookies_from_file('export_cookies.json')"
  3. 以後は自動投稿が使える

GitHub Actions では:
  base64 -w0 x_cookies.json の出力を X_COOKIES Secret に登録する
"""
import base64
import json
import os
import random
import time
from pathlib import Path

COOKIE_FILE = Path(os.environ.get("X_COOKIE_FILE", "data/x_cookies.json"))
DISCORD_INVITE = os.environ.get("DISCORD_INVITE_URL", "")
CHANNEL = "x"
MAX_POSTS_PER_RUN = 5
POST_INTERVAL_MIN = 60   # seconds between posts
POST_INTERVAL_MAX = 180


def _load_cookies() -> list[dict] | None:
    # 1. 環境変数（GitHub Actions Secret）
    raw = os.environ.get("X_COOKIES", "")
    if raw:
        try:
            return json.loads(base64.b64decode(raw).decode())
        except Exception as e:
            print(f"[X] X_COOKIES decode error: {e}")

    # 2. ローカルファイル
    if COOKIE_FILE.exists():
        return json.loads(COOKIE_FILE.read_text())

    return None


def _normalize_cookie(c: dict) -> dict:
    """Export形式（EditThisCookie等）をPlaywright形式に変換。"""
    normalized = {
        "name": c.get("name", c.get("Name", "")),
        "value": c.get("value", c.get("Value", "")),
        "domain": c.get("domain", c.get("Domain", "")),
        "path": c.get("path", c.get("Path", "/")),
        "secure": c.get("secure", c.get("Secure", False)),
        "httpOnly": c.get("httpOnly", c.get("HttpOnly", False)),
    }
    domain = normalized["domain"]
    if not domain.startswith(".") and not domain.startswith("x.com"):
        normalized["domain"] = "." + domain.replace("twitter.com", "x.com")
    else:
        normalized["domain"] = domain.replace("twitter.com", "x.com")

    same_site = c.get("sameSite", c.get("SameSite", "Lax"))
    if same_site not in ("Strict", "Lax", "None"):
        same_site = "Lax"
    normalized["sameSite"] = same_site

    exp = c.get("expirationDate", c.get("expires", c.get("Expires")))
    if exp:
        normalized["expires"] = int(exp)

    return normalized


_X_LIMIT = 270          # 安全マージンを取った上限（Xの制限は280）
_URL_WEIGHT = 23        # XはURLを常に23文字換算（t.co短縮）
_NAME_MAX = 30          # 商品名の最大表示文字数


def _x_len(text: str) -> int:
    """X の文字数カウント: URL は 23文字固定、それ以外は文字数そのまま。"""
    import re
    url_pattern = re.compile(r"https?://\S+")
    urls = url_pattern.findall(text)
    no_url = url_pattern.sub("", text)
    return len(no_url) + len(urls) * _URL_WEIGHT


def _truncate(name: str, max_len: int = _NAME_MAX) -> str:
    return name[:max_len] + "…" if len(name) > max_len else name


def _build_tweet_text(product: dict, with_affiliate: bool = True) -> str:
    """280文字制限を守りながらツイートを組み立てる。

    優先度: 商品名＋価格＋発売日 > アフィリエイトURL > ハッシュタグ > Discord招待
    """
    name = _truncate(product.get("clean_name") or product.get("name", ""))
    price = product.get("play_price")
    release_date = product.get("release_date") or product.get("release_month", "")
    ip_tag = product.get("ip_tag", "")
    amazon_url = product.get("amazon_url", "")
    is_reprint = product.get("is_reprint", False)

    # --- 必須ブロック（常に含める）---
    head = ("【再販】" if is_reprint else "") + f"🎰 {name}"
    meta_parts = []
    if release_date:
        meta_parts.append(f"📅 {release_date}")
    if price:
        meta_parts.append(f"💴 {price}円")
    meta = "　".join(meta_parts)

    base = f"{head}\n{meta}" if meta else head

    # --- オプションブロック（文字数が許す範囲で追加）---
    hashtags = "#ガチャガチャ #カプセルトイ"
    if ip_tag:
        hashtags += f" #{ip_tag.replace(' ', '')}"

    affiliate_line = f"🛒 Amazon（PR）\n{amazon_url}" if (with_affiliate and amazon_url) else ""
    discord_line = f"💬 Discord\n{DISCORD_INVITE}" if DISCORD_INVITE else ""

    # 優先度順に追加し、超えたら省略
    candidates = [
        ("affiliate", f"\n{affiliate_line}"),
        ("hashtags",  f"\n{hashtags}"),
        ("discord",   f"\n{discord_line}"),
    ]

    result = base
    for key, block in candidates:
        if not block.strip():
            continue
        if _x_len(result + block) <= _X_LIMIT:
            result += block
        else:
            # hashtags だけは短縮版で再挑戦
            if key == "hashtags":
                short = "\n#ガチャガチャ"
                if _x_len(result + short) <= _X_LIMIT:
                    result += short

    return result


def _check_login(page) -> bool:
    url = page.url
    return "login" not in url and "i/flow" not in url


def post_to_x(products: list[dict]) -> int:
    cookies = _load_cookies()
    if not cookies:
        print("[X] クッキーが見つかりません。X_COOKIES 環境変数または data/x_cookies.json を設定してください。")
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[X] playwright がインストールされていません: pip install playwright && playwright install chromium")
        return 0

    posted = 0
    targets = products[:MAX_POSTS_PER_RUN]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        context.add_cookies([_normalize_cookie(c) for c in cookies])
        page = context.new_page()

        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        if not _check_login(page):
            print("[X] ログインされていません。クッキーを更新してください。")
            browser.close()
            return 0

        for p in targets:
            tweet_text = _build_tweet_text(p)
            try:
                page.goto("https://x.com/compose/tweet", wait_until="domcontentloaded", timeout=20000)
                time.sleep(2)

                # テキスト入力エリア
                editor = page.wait_for_selector(
                    '[data-testid="tweetTextarea_0"], [role="textbox"][data-offset-key]',
                    timeout=10000,
                )
                editor.click()
                page.keyboard.type(tweet_text, delay=50)
                time.sleep(1)

                # 投稿ボタン
                post_btn = page.wait_for_selector(
                    '[data-testid="tweetButtonInline"], [data-testid="tweetButton"]',
                    timeout=5000,
                )
                post_btn.click()
                time.sleep(2)

                posted += 1
                print(f"[X] 投稿成功: {p.get('clean_name', '')[:30]}")

                if posted < len(targets):
                    sleep_sec = random.uniform(POST_INTERVAL_MIN, POST_INTERVAL_MAX)
                    print(f"[X] 次の投稿まで {sleep_sec:.0f}秒 待機...")
                    time.sleep(sleep_sec)

            except Exception as e:
                print(f"[X] 投稿エラー: {e}")

        browser.close()

    return posted


def save_cookies_from_file(export_path: str):
    """EditThisCookie等のエクスポートファイルをdata/x_cookies.jsonに変換保存。"""
    data = json.loads(Path(export_path).read_text())
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Saved {len(data)} cookies to {COOKIE_FILE}")

    # base64 出力（GitHub Secrets 登録用）
    b64 = base64.b64encode(json.dumps(data).encode()).decode()
    print(f"\nGitHub Secrets 登録用 X_COOKIES の値（以下をコピー）:\n{b64[:80]}...")
