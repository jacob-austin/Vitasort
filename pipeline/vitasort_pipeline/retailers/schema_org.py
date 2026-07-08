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


def _extract_image(doc):
    for d in _walk(doc):
        types = d.get("@type", "")
        types = types if isinstance(types, list) else [types]
        if "Product" in types and d.get("image"):
            img = d["image"]
            if isinstance(img, list):
                img = img[0]
            if isinstance(img, dict):
                img = img.get("url")
            if isinstance(img, str) and img.startswith("http"):
                return img
    return None


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
            offer["image"] = _extract_image(doc)
            return offer
    # Fallbacks for pages without Product JSON-LD (structured meta the site
    # publishes intentionally: itemprop/og price tags, og:image, retailer CDN imgs)
    html = resp.text
    m = (re.search(r'itemprop=["\']price["\'][^>]*content=["\']([\d.,]+)', html)
         or re.search(r'property=["\']og:price:amount["\'][^>]*content=["\']([\d.,]+)', html)
         or re.search(r'property=["\']product:price:amount["\'][^>]*content=["\']([\d.,]+)', html))
    if m:
        try:
            price = float(m.group(1).replace(",", ""))
        except ValueError:
            price = None
        if price:
            return {"price": price, "in_stock": "outofstock" not in html.lower().replace(" ", ""),
                    "image": _fallback_image(html)}
    print(f"  no structured price found at {listing['url']}")
    return None


def _fallback_image(html: str):
    m = re.search(
        r'https://cloudinary\.images-iherb\.com/image/upload/[^"\'\s>]+/images/[a-z0-9]+/[a-z0-9]+/l/\d+\.jpg',
        html)
    if m:
        return m.group(0)
    m = re.search(r'property=["\']og:image["\'][^>]*content=["\'](https?://[^"\']+)', html)
    return m.group(1) if m else None


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
            offer["image"] = _extract_image(doc)
            return offer
    # Fallbacks for pages without Product JSON-LD (structured meta the site
    # publishes intentionally: itemprop/og price tags, og:image, retailer CDN imgs)
    html = resp.text
    m = (re.search(r'itemprop=["\']price["\'][^>]*content=["\']([\d.,]+)', html)
         or re.search(r'property=["\']og:price:amount["\'][^>]*content=["\']([\d.,]+)', html)
         or re.search(r'property=["\']product:price:amount["\'][^>]*content=["\']([\d.,]+)', html))
    if m:
        try:
            price = float(m.group(1).replace(",", ""))
        except ValueError:
            price = None
        if price:
            return {"price": price, "in_stock": "outofstock" not in html.lower().replace(" ", ""),
                    "image": _fallback_image(html)}
    print(f"  no structured price found at {listing['url']}")
    return None


def _fallback_image(html: str):
    m = re.search(r'images-iherb\.com/image/upload/[^"\'\s>]+/images/[a-z0-9]+/[a-z0-9]+/l/\d+\.jpg', html)
    if m:
        return "https://cloudinary." + m.group(0).split("cloudinary.")[-1] if "cloudinary" not in m.group(0) else "https://" + m.group(0)
    m = re.search(r'property=["\']og:image["\'][^>]*content=["\'](https?://[^"\']+)', html)
    return m.group(1) if m else None
