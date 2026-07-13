#!/usr/bin/env python3
"""既存DB内の全商品について、Amazon/Rakutenアフィリエイトリンクだけを再生成する。
affiliate.pyのロジック変更後、再スクレイプせずにリンクだけ更新したい場合に使う。

Usage:
  MOSHIMO_AFFILIATE_ID=xxx AMAZON_AFFILIATE_TAG=xxx python3 scripts/refresh_affiliate_links.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from store.db import get_conn, upsert_affiliate
from pipeline.affiliate import generate_links


def main():
    conn = get_conn()
    rows = conn.execute("SELECT id, clean_name, maker FROM products").fetchall()
    print(f"対象商品数: {len(rows)}")
    for i, row in enumerate(rows, 1):
        links = generate_links(row["clean_name"], row["maker"])
        upsert_affiliate(conn, row["id"], "amazon", links["amazon"])
        upsert_affiliate(conn, row["id"], "rakuten", links["rakuten"])
        if i % 200 == 0:
            print(f"  {i}/{len(rows)}...")
    conn.commit()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
