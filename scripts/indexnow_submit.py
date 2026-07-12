#!/usr/bin/env python3
"""IndexNow へサイトの全URLを通知する。

サイトデプロイ後に実行する想定。site/src/data/index.json の月一覧から
月別ページ + トップページ + aboutページのURLリストを組み立てて送信する。

Usage:
  python scripts/indexnow_submit.py
"""
import json
import sys
from pathlib import Path

import httpx

HOST = "gacha-calendar-20p.pages.dev"
INDEXNOW_KEY = "44333e077a9bd790f68089d23872cc69"
BASE_URL = f"https://{HOST}"

ROOT = Path(__file__).resolve().parent.parent
INDEX_JSON = ROOT / "site" / "src" / "data" / "index.json"


def build_url_list() -> list[str]:
    urls = [f"{BASE_URL}/", f"{BASE_URL}/about/"]
    if INDEX_JSON.exists():
        data = json.loads(INDEX_JSON.read_text())
        for m in data.get("months", []):
            urls.append(f"{BASE_URL}/{m['month']}/")
    return urls


def submit(urls: list[str]) -> None:
    payload = {
        "host": HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{BASE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }
    res = httpx.post(
        "https://api.indexnow.org/indexnow",
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )
    print(f"IndexNow response: {res.status_code}")
    if res.status_code not in (200, 202):
        print(res.text[:500])
        sys.exit(1)


def main() -> None:
    urls = build_url_list()
    print(f"Submitting {len(urls)} URLs to IndexNow...")
    submit(urls)
    print("Done.")


if __name__ == "__main__":
    main()
