"""Generate affiliate search links for Amazon/Rakuten via もしもアフィリエイト."""
import os
import urllib.parse

MOSHIMO_RAKUTEN_PRODUCT_ID = "54"
MOSHIMO_AMAZON_PRODUCT_ID = "170"


def _amazon_tag() -> str:
    return os.environ.get("AMAZON_AFFILIATE_TAG", "")


def _moshimo_id() -> str:
    return os.environ.get("MOSHIMO_AFFILIATE_ID", "")


def _moshimo_wrap(url: str, moshimo_p_id: str, moshimo_pc_id: str, moshimo_pl_id: str) -> str:
    if not _moshimo_id():
        return url
    base = "https://af.moshimo.com/af/c/click"
    params = {
        "a_id": _moshimo_id(),
        "p_id": moshimo_p_id,
        "pc_id": moshimo_pc_id,
        "pl_id": moshimo_pl_id,
        "url": url,
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def amazon_search_url(keyword: str) -> str:
    query = urllib.parse.quote(keyword)
    base = f"https://www.amazon.co.jp/s?k={query}"
    tag = _amazon_tag()
    if tag:
        base += f"&tag={tag}"
    return _moshimo_wrap(base, "170", "185", "4062")


def rakuten_search_url(keyword: str) -> str:
    encoded = urllib.parse.quote(keyword)
    base = f"https://search.rakuten.co.jp/search/mall/{encoded}/"
    return _moshimo_wrap(base, "54", "67", "559")


def generate_links(clean_name: str, maker: str | None = None) -> dict[str, str]:
    keyword = f"{maker} {clean_name}".strip() if maker else clean_name
    return {
        "amazon": amazon_search_url(keyword),
        "rakuten": rakuten_search_url(keyword),
    }
