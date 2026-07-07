"""Generic adapter: extract price from schema.org Product JSON-LD.

Most reputable retailers (iHerb, Myprotein, brand stores on Shopify, etc.)
embed <script type="application/ld+json"> with a Product/Offer block for SEO.
This reads structured data the site intentionally publishes — no HTML guessing.
"""
import json
import re

from .base import polite_get

_LDJSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)


def _walk(node):
    """Yield every dict in a nested JSON structure."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _extract_offer(doc):
    for d in _walk(doc):
        types = d.get("@type", "")
        types = types if isinstance(types, list) else [types]
        if "Offer" in types or "AggregateOffer" in types:
            price = d.get("price") or d.get("lowPrice")
            if price is None:
                continue
            try:
                price = float(str(price).replace(",", "").replace("$", ""))
            except ValueError:
                continue
            availability = str(d.get("availability", "")).lower()
            in_stock = "outofstock" not in availability.replace(" ", "")
            return {"price": price, "in_stock": in_stock}
    return None


def fetch_price(listing: dict):
    resp = polite_get(listing["url"])
    if resp is None:
        return None
    for match in _LDJSON_RE.findall(resp.text):
        try:
            doc = json.loads(match.strip())
        except json.JSONDecodeError:
            continue
        offer = _extract_offer(doc)
        if offer:
            return offer
    print(f"  no schema.org offer found at {listing['url']}")
    return None
