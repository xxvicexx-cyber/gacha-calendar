"""Discord Webhook による速報配信。"""
import os
import httpx

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

CHANNEL = "discord"


def _price_label(price: int | None) -> str:
    return f"{price}円" if price else "価格不明"


def _build_embed(product: dict, is_new: bool, changes: list[str]) -> dict:
    if is_new:
        title = f"🆕 新着：{product.get('clean_name') or product.get('name', '')}"
        color = 0x00B0F4
        desc_parts = []
    else:
        title = f"⚠️ 変更：{product.get('clean_name') or product.get('name', '')}"
        color = 0xFF8C00
        change_labels = {
            "release_month": "発売月",
            "release_date": "発売日",
            "release_text": "変更詳細",
            "play_price": "価格",
        }
        desc_parts = ["変更項目: " + "、".join(change_labels.get(c, c) for c in changes)]

    meta = []
    if product.get("maker"):
        meta.append(f"メーカー: {product['maker']}")
    if product.get("release_date"):
        meta.append(f"発売日: {product['release_date']}")
    elif product.get("release_month"):
        meta.append(f"発売月: {product['release_month']}")
    meta.append(f"価格: {_price_label(product.get('play_price'))}")
    if product.get("is_reprint"):
        meta.append("《再販》")
    if product.get("overseas_ng"):
        meta.append("【予約海外NG】")

    desc_parts.extend(meta)
    if product.get("release_text"):
        desc_parts.append(f"備考: {product['release_text']}")

    embed = {
        "title": title,
        "description": "\n".join(desc_parts),
        "color": color,
        "url": product.get("detail_url") or "",
    }

    if product.get("amazon_url"):
        embed["fields"] = [
            {"name": "Amazon", "value": f"[検索]({product['amazon_url']})", "inline": True},
        ]
        if product.get("rakuten_url"):
            embed["fields"].append(
                {"name": "楽天", "value": f"[検索]({product['rakuten_url']})", "inline": True}
            )

    if product.get("image_url"):
        embed["thumbnail"] = {"url": product["image_url"]}

    return embed


def post_to_discord(products: list[dict]) -> int:
    if not WEBHOOK_URL:
        print("[DISCORD] DISCORD_WEBHOOK_URL not set, skipping")
        return 0
    if not products:
        return 0

    # Discord allows up to 10 embeds per message
    posted = 0
    for i in range(0, len(products), 10):
        batch = products[i : i + 10]
        embeds = []
        for p in batch:
            embed = _build_embed(p, p.get("_is_new", False), p.get("_changes", []))
            embeds.append(embed)

        payload = {"embeds": embeds}
        try:
            resp = httpx.post(WEBHOOK_URL, json=payload, timeout=10)
            resp.raise_for_status()
            posted += len(batch)
        except httpx.HTTPError as e:
            print(f"[DISCORD ERROR] {e}")

    return posted
