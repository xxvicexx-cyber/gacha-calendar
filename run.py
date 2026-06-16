#!/usr/bin/env python3
"""メインパイプライン: 収集 → 正規化 → DB保存 → 速報配信 → サイトデータ生成。

Usage:
  python run.py [--skip-scrape] [--skip-notify] [--skip-site]
"""
import argparse
import sys
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from scrapers.amuzu import scrape_all_schedules
from scrapers.amuzu_changes import scrape_changes
from scrapers.base import BaseScraper
from pipeline.normalize import parse_item_name
from pipeline.affiliate import generate_links
from store.db import (
    init_db, get_conn, upsert_product, upsert_affiliate,
    get_unposted, mark_posted, get_products_by_month, get_months,
)
from distribute.discord import post_to_discord, CHANNEL


def process_items(raw_items: list[dict], conn) -> list[tuple]:
    results = []
    for raw in raw_items:
        parsed = parse_item_name(raw["name"], url_month=raw.get("_url_month"))

        product = {
            "source_code": raw["source_code"],
            "name": raw["name"],
            "clean_name": parsed["clean_name"],
            "maker": parsed["maker"],
            "play_price": raw.get("play_price"),
            "release_month": parsed["release_month"],
            "release_date": raw.get("release_date"),
            "release_text": parsed.get("release_text"),
            "is_reprint": parsed["is_reprint"],
            "overseas_ng": parsed["overseas_ng"],
            "lot_qty": parsed.get("lot_qty"),
            "ip_tag": parsed.get("ip_tag"),
            "image_url": raw.get("image_url"),
            "detail_url": raw.get("detail_url"),
            "source": "amuzu",
            "source_priority": 10,
        }

        product_id, is_new, changes = upsert_product(conn, product)

        # Generate affiliate links
        links = generate_links(product["clean_name"], product["maker"])
        for asp, url in links.items():
            upsert_affiliate(conn, product_id, asp, url)

        results.append((product_id, is_new, changes, product))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-notify", action="store_true")
    parser.add_argument("--skip-site", action="store_true")
    parser.add_argument("--months-ahead", type=int, default=5)
    args = parser.parse_args()

    init_db()
    conn = get_conn()

    # --- 1. Scrape ---
    if not args.skip_scrape:
        print("=== Scraping あミューズ schedules ===")
        with BaseScraper() as scraper:
            raw_items = scrape_all_schedules(scraper, months_ahead=args.months_ahead)
            change_items = scrape_changes(scraper)

        all_raw = raw_items + change_items
        print(f"Total scraped: {len(all_raw)}")

        print("=== Processing & saving to DB ===")
        with conn:
            results = process_items(all_raw, conn)

        new_count = sum(1 for _, is_new, _, _ in results if is_new)
        changed_count = sum(1 for _, _, changes, _ in results if changes)
        print(f"New: {new_count}, Changed: {changed_count}")
    else:
        print("=== Skipping scrape ===")

    # --- 2. Discord notifications ---
    if not args.skip_notify:
        print("=== Sending Discord notifications ===")
        unposted = get_unposted(conn, CHANNEL)
        if unposted:
            # Attach affiliate URLs
            notify_list = []
            for row in unposted:
                p = dict(row)
                p["_is_new"] = row["first_seen_at"] is not None
                p["_changes"] = []  # simplified: mark all as new for Discord
                notify_list.append(p)

            posted = post_to_discord(notify_list)
            print(f"Posted {posted} items to Discord")

            with conn:
                for row in unposted[:posted]:
                    mark_posted(conn, row["id"], CHANNEL)
        else:
            print("No new items to notify")

    # --- 3. Generate site data ---
    if not args.skip_site:
        print("=== Generating site data ===")
        generate_site_data(conn)

    conn.close()
    print("Done.")


def generate_site_data(conn):
    import json
    from datetime import datetime

    out_dir = Path(__file__).parent / "site" / "src" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    months = get_months(conn)
    all_data = {}

    for month in months:
        rows = get_products_by_month(conn, month)
        products = []
        for r in rows:
            products.append({
                "id": r["id"],
                "source_code": r["source_code"],
                "name": r["name"],
                "clean_name": r["clean_name"],
                "maker": r["maker"],
                "play_price": r["play_price"],
                "release_month": r["release_month"],
                "release_date": r["release_date"],
                "is_reprint": bool(r["is_reprint"]),
                "overseas_ng": bool(r["overseas_ng"]),
                "ip_tag": r["ip_tag"],
                "image_url": r["image_url"],
                "detail_url": r["detail_url"],
                "amazon_url": r["amazon_url"],
                "rakuten_url": r["rakuten_url"],
            })
        all_data[month] = products

    # Write per-month JSON files
    for month, products in all_data.items():
        (out_dir / f"{month}.json").write_text(
            json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Write index (months list + counts)
    index = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "months": [
            {"month": m, "count": len(all_data[m])} for m in sorted(all_data.keys())
        ],
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Site data written: {len(months)} months, {sum(len(v) for v in all_data.values())} total products")


if __name__ == "__main__":
    main()
