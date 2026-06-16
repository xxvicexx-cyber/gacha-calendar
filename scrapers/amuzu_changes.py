"""あミューズ 発売日変更・中止一覧スクレイパー。

SCHEDULE_CHANGE カテゴリは p-schedule-item と同じ構造。
items は 0件の場合もある（その場合はスキップ）。
"""
from bs4 import BeautifulSoup

from scrapers.amuzu import _parse_item_card, BASE_URL
from scrapers.base import BaseScraper

CHANGE_CATEGORY = "SCHEDULE_CHANGE"


def scrape_changes(scraper: BaseScraper) -> list[dict]:
    url = f"{BASE_URL}/category/{CHANGE_CATEGORY}/"
    resp = scraper.get(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    cards = soup.select("a.p-schedule-item")
    items = []
    for card in cards:
        item = _parse_item_card(card, url_month=None)
        if item:
            item["_is_change"] = True
            items.append(item)

    print(f"[SCHEDULE_CHANGE] {len(items)} items")
    return items
