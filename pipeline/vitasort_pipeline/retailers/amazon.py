"""Amazon adapter via the official Product Advertising API (PA-API 5).

Scraping Amazon violates their ToS and gets blocked quickly; the sanctioned
route is PA-API with an Amazon Associates account (free, and links earn
affiliate commission — the PCPartPicker model).

Setup:
  1. Join Amazon Associates: https://affiliate-program.amazon.com
  2. Request PA-API access, get an access key / secret key / partner tag
  3. pip install python-amazon-paapi
  4. Set env vars: AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG
     (in GitHub Actions: repo Settings → Secrets)

Without credentials this adapter returns None and the pipeline falls back to
the last known / seed price, so the build always succeeds.
"""
import os

_client = None
_warned = False


def _get_client():
    global _client, _warned
    if _client is not None:
        return _client
    access = os.environ.get("AMAZON_ACCESS_KEY")
    secret = os.environ.get("AMAZON_SECRET_KEY")
    tag = os.environ.get("AMAZON_PARTNER_TAG")
    if not (access and secret and tag):
        if not _warned:
            print("  Amazon PA-API credentials not set; using fallback prices for Amazon listings")
            _warned = True
        return None
    try:
        from amazon_paapi import AmazonApi  # python-amazon-paapi
    except ImportError:
        if not _warned:
            print("  python-amazon-paapi not installed; using fallback prices for Amazon listings")
            _warned = True
        return None
    _client = AmazonApi(access, secret, tag, "US")
    return _client


def fetch_price(listing: dict):
    client = _get_client()
    if client is None or "asin" not in listing:
        return None
    try:
        items = client.get_items(listing["asin"])
        item = items[0]
        offer = item.offers.listings[0]
        image = None
        try:
            image = item.images.primary.large.url
        except AttributeError:
            pass
        return {
            "price": float(offer.price.amount),
            "in_stock": offer.availability.type == "Now",
            "image": image,
        }
    except Exception as e:  # PA-API raises many exception types; never break the build
        print(f"  PA-API lookup failed for {listing.get('asin')}: {e}")
        return None
