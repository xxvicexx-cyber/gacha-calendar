"""Normalize product names and extract structured fields from あミューズ item titles."""
import re
import unicodedata

BASE_YEAR = 2026

KNOWN_NON_MAKER = re.compile(
    r"^(?:\d+月|二次予約|一次予約|三次予約|四次予約|先行|予約|再入荷|追加|新規|受注|発売|入荷|ﾊｰﾄ).*"
)
OVERSEAS_RE = re.compile(r"海外NG|OVERSEAS.*NG|予約海外NG", re.IGNORECASE)
CATEGORY_SUFFIX_RE = re.compile(r"カプセルトイ\s*$")
LOT_RE = re.compile(r"[（(](\d+)個入り?[）)]")

IP_KEYWORDS = {
    "サンリオ": ["サンリオ", "ハローキティ", "シナモロール", "マイメロ", "ポムポムプリン", "クロミ"],
    "ポケモン": ["ポケモン", "ピカチュウ", "イーブイ"],
    "ディズニー": ["ディズニー", "ミッキー", "ミニー", "プーさん", "ツムツム"],
    "ジブリ": ["ジブリ", "となりのトトロ", "千と千尋", "もののけ"],
    "鬼滅の刃": ["鬼滅"],
    "呪術廻戦": ["呪術廻戦"],
    "ワンピース": ["ワンピース"],
    "ドラゴンボール": ["ドラゴンボール"],
    "モンチッチ": ["モンチッチ"],
    "すみっコぐらし": ["すみっコぐらし"],
    "ちいかわ": ["ちいかわ"],
}


def normalize_text(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip()


def extract_month(text: str) -> int | None:
    m = re.search(r"(\d+)月", text)
    return int(m.group(1)) if m else None


def detect_ip(name: str) -> str | None:
    for ip, keywords in IP_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return ip
    return None


def parse_item_name(raw_name: str, url_month: int | None = None) -> dict:
    name = normalize_text(raw_name)
    result = {
        "name": raw_name,
        "clean_name": "",
        "release_month": None,
        "maker": None,
        "is_reprint": "《再販》" in name,
        "overseas_ng": bool(OVERSEAS_RE.search(name)),
        "lot_qty": None,
        "release_text": None,
        "ip_tag": None,
    }

    # 1. Detect delay notice ※N月発売へ延期※
    delay_m = re.search(r"※(\d+月[^※]*)へ延期※", name)
    if delay_m:
        result["release_text"] = delay_m.group(0)
        month_num = extract_month(delay_m.group(1))
        if month_num:
            result["release_month"] = f"{BASE_YEAR}-{month_num:02d}"

    # 2. Strip preamble tokens from working copy
    work = name
    work = re.sub(r"^(※[^※]+※\s*)+", "", work)
    work = re.sub(r"^(【[^【】]+】\s*)+", "", work)
    work = work.replace("《再販》", "").strip()

    # 3. Extract 【...】 tags remaining (after the name)
    brackets = re.findall(r"【([^【】]+)】", work)
    maker_candidates = []
    for b in brackets:
        b_norm = normalize_text(b)
        if OVERSEAS_RE.search(b_norm):
            continue
        if KNOWN_NON_MAKER.match(b_norm):
            continue
        maker_candidates.append(b_norm)

    if maker_candidates:
        result["maker"] = maker_candidates[-1]

    # 4. If release_month not set from delay, try 【N月発売】 in original name
    if not result["release_month"]:
        month_tag = re.search(r"【(\d+)月発売】", name)
        if month_tag:
            result["release_month"] = f"{BASE_YEAR}-{int(month_tag.group(1)):02d}"
        elif url_month:
            result["release_month"] = f"{BASE_YEAR}-{url_month:02d}"

    # 5. Clean name: remove all 【...】, 《再販》, lot qty
    clean = re.sub(r"【[^【】]+】", "", work).strip()
    lot_m = LOT_RE.search(clean)
    if lot_m:
        result["lot_qty"] = int(lot_m.group(1))
        clean = clean.replace(lot_m.group(0), "").strip()
    clean = CATEGORY_SUFFIX_RE.sub("", clean).strip()
    result["clean_name"] = clean

    # 6. IP tag
    result["ip_tag"] = detect_ip(name)

    return result
