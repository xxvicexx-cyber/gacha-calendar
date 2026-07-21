import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "data" / "gacha.db"))


def get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    schema = Path(__file__).parent / "schema.sql"
    with get_conn() as conn:
        conn.executescript(schema.read_text())


def upsert_product(conn: sqlite3.Connection, data: dict) -> tuple[int, bool, list[str]]:
    """Insert or update a product. Returns (product_id, is_new, changed_fields)."""
    now = datetime.utcnow().isoformat()
    row = conn.execute(
        "SELECT * FROM products WHERE source_code = ?", (data["source_code"],)
    ).fetchone()

    tracked_fields = ("release_month", "release_date", "release_text", "play_price", "maker", "clean_name")
    changes = []

    if row is None:
        conn.execute(
            """INSERT INTO products
               (source_code, jan_code, name, clean_name, series, maker, category,
                play_price, release_month, release_date, release_text,
                is_reprint, overseas_ng, capsule_size, lot_qty, ip_tag,
                image_url, detail_url, source, source_priority, first_seen_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("source_code"), data.get("jan_code"), data.get("name"),
                data.get("clean_name"), data.get("series"), data.get("maker"),
                data.get("category", "gacha"), data.get("play_price"),
                data.get("release_month"), data.get("release_date"),
                data.get("release_text"), int(data.get("is_reprint", False)),
                int(data.get("overseas_ng", False)), data.get("capsule_size"),
                data.get("lot_qty"), data.get("ip_tag"),
                data.get("image_url"), data.get("detail_url"),
                data.get("source", "amuzu"), data.get("source_priority", 10),
                now, now,
            ),
        )
        product_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return product_id, True, []

    product_id = row["id"]
    for field in tracked_fields:
        old = row[field]
        new = data.get(field)
        if old != new and new is not None:
            changes.append(field)
            conn.execute(
                """INSERT OR IGNORE INTO release_changes (source_code, changed_at, field, old_value, new_value)
                   VALUES (?, ?, ?, ?, ?)""",
                (data["source_code"], now, field, str(old) if old else None, str(new)),
            )

    if changes:
        sets = ", ".join(f"{f} = ?" for f in tracked_fields if data.get(f) is not None)
        vals = [data[f] for f in tracked_fields if data.get(f) is not None]
        if sets:
            vals.append(now)
            vals.append(data["source_code"])
            conn.execute(f"UPDATE products SET {sets}, updated_at = ? WHERE source_code = ?", vals)

    return product_id, False, changes


def get_unposted(conn: sqlite3.Connection, channel: str) -> list[sqlite3.Row]:
    """New products and changed products not yet posted to channel."""
    return conn.execute(
        """SELECT p.*,
               CASE WHEN rc.source_code IS NOT NULL THEN 1 ELSE 0 END as has_change,
               al_amazon.url as amazon_url,
               al_rakuten.url as rakuten_url
           FROM products p
           LEFT JOIN (
               SELECT DISTINCT source_code FROM release_changes
               WHERE changed_at > datetime('now', '-1 day')
           ) rc ON p.source_code = rc.source_code
           LEFT JOIN affiliate_links al_amazon
               ON p.id = al_amazon.product_id AND al_amazon.asp = 'amazon'
           LEFT JOIN affiliate_links al_rakuten
               ON p.id = al_rakuten.product_id AND al_rakuten.asp = 'rakuten'
           WHERE p.id NOT IN (SELECT product_id FROM post_log WHERE channel = ?)
             AND (
               p.first_seen_at > datetime('now', '-1 day')
               OR rc.source_code IS NOT NULL
             )
           ORDER BY p.release_date ASC, p.release_month ASC
           LIMIT 20""",
        (channel,),
    ).fetchall()


def mark_posted(conn: sqlite3.Connection, product_id: int, channel: str):
    conn.execute(
        "INSERT OR IGNORE INTO post_log (product_id, channel) VALUES (?, ?)",
        (product_id, channel),
    )


def upsert_affiliate(conn: sqlite3.Connection, product_id: int, asp: str, url: str):
    conn.execute(
        """INSERT INTO affiliate_links (product_id, asp, url, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(product_id, asp) DO UPDATE SET url=excluded.url, updated_at=excluded.updated_at""",
        (product_id, asp, url, datetime.utcnow().isoformat()),
    )


def get_affiliate_url(conn: sqlite3.Connection, product_id: int, asp: str) -> str | None:
    row = conn.execute(
        "SELECT url FROM affiliate_links WHERE product_id=? AND asp=?", (product_id, asp),
    ).fetchone()
    return row["url"] if row else None


def get_products_by_month(conn: sqlite3.Connection, month: str) -> list[sqlite3.Row]:
    """month: 'YYYY-MM'"""
    return conn.execute(
        """SELECT p.*, al_amazon.url as amazon_url, al_rakuten.url as rakuten_url
           FROM products p
           LEFT JOIN affiliate_links al_amazon ON p.id = al_amazon.product_id AND al_amazon.asp = 'amazon'
           LEFT JOIN affiliate_links al_rakuten ON p.id = al_rakuten.product_id AND al_rakuten.asp = 'rakuten'
           WHERE p.release_month = ?
           ORDER BY p.release_date ASC, p.clean_name ASC""",
        (month,),
    ).fetchall()


def get_months(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT release_month FROM products WHERE release_month IS NOT NULL ORDER BY release_month"
    ).fetchall()
    return [r[0] for r in rows]
