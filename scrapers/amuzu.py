"""あミューズ月別入荷スケジュールスクレイパー。

SCHEDULE_202607 形式のカテゴリページを巡回し、p-schedule-item カードを解析する。
CAPSULE_TOY_009_N（予約月別）も同一ロジックで対応。
"""
import re
from datetime import datetime, date

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

BASE_URL = "https://www.a-muzu.com"
_PRICE_RE = re.compile(r"(\d+)yen\.gif")
_DATE_RE = re.compile(r"(\d{4})/(\d{2})/(\d{2})")


def _parse_play_price(img_src: str) -> int | None:
    m = _PRICE_RE.search(img_src)
    return int(m.group(1)) if m else None


def _parse_item_card(card, url_month: int | None = None) -> dict | None:
    try:
        href = card.get("href", "")
        title = card.get("title", "").strip()

        # Release date
        date_tag = card.select_one(".p-schedule-item__arrival-date")
        release_date_str = date_tag.get_text(strip=True) if date_tag else None
        release_date = None
        if release_date_str:
            m = _DATE_RE.match(release_date_str)
            if m:
                release_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()

        # Play price from price gif
        price_img = card.select_one(".p-schedule-item__arrival-type img")
        play_price = _parse_play_price(price_img["src"]) if price_img else None

        # Product image
        prod_img = card.select_one(".p-schedule-item__product-image img")
        image_url = (BASE_URL + prod_img["src"]) if prod_img else None

        # Source code from product-code text
        code_tag = card.select_one(".p-schedule-item__product-code")
        source_code = None
        if code_tag:
            m = re.search(r"C\d+", code_tag.get_text())
            if m:
                source_code = m.group(0)

        # Fallback: extract code from href
        if not source_code:
            m = re.search(r"/(C\d+)\.html", href)
            if m:
                source_code = m.group(1)

        if not source_code:
            return None

        return {
            "source_code": source_code,
            "name": title,
            "detail_url": href,
            "image_url": image_url,
            "play_price": play_price,
            "release_date": release_date,
            "_url_month": url_month,
        }
    except Exception as e:
        print(f"[WARN] parse_item_card error: {e}")
        return None


def scrape_category(scraper: BaseScraper, category: str) -> list[dict]:
    """Scrape all pages of a given category (e.g. 'SCHEDULE_202607')."""
    url_month = None
    m = re.search(r"SCHEDULE_\d{4}(\d{2})", category)
    if not m:
        m = re.search(r"CAPSULE_TOY_009_(\d+)", category)
    if m:
        url_month = int(m.group(1))

    base_cat_url = f"{BASE_URL}/category/{category}/"
    items: list[dict] = []
    page = 1

    while True:
        if page == 1:
            url = base_cat_url
        else:
            url = (
                f"{base_cat_url}?SEARCH_MAX_ROW_LIST=60"
                f"&item_list_mode=1&sort_order=1&request=page&next_page={page}"
            )

        resp = scraper.get(url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("a.p-schedule-item")
        if not cards:
            break

        for card in cards:
            item = _parse_item_card(card, url_month)
            if item:
                items.append(item)

        # Check for next page
        next_links = soup.select(".c-pager__link:not(.is-current)")
        has_next = any(f"next_page={page + 1}" in (l.get("href") or "") for l in next_links)
        if not has_next:
            break
        page += 1
        print(f"  [{category}] page {page}, {len(items)} items so far...")

    print(f"[{category}] total {len(items)} items")
    return items


def get_schedule_months(months_ahead: int = 5) -> list[str]:
    """Generate category codes for the next N months from current month."""
    now = datetime.now()
    categories = []
    year, month = now.year, now.month
    for _ in range(months_ahead):
        categories.append(f"SCHEDULE_{year}{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return categories


def scrape_all_schedules(scraper: BaseScraper, months_ahead: int = 5) -> list[dict]:
    all_items = []
    for cat in get_schedule_months(months_ahead):
        items = scrape_category(scraper, cat)
        all_items.extend(items)
    return all_items
