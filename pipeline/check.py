#!/usr/bin/env python3
"""Diagnose every data source: robots.txt, fetchability, extraction.

  python3 pipeline/check.py

For each fetchable listing, prints one line:
  OK        price extracted (shows price / rating / image found)
  ROBOTS    robots.txt disallows this page (respected; listing stays link-only)
  BLOCKED   HTTP error / bot detection
  NO-DATA   page fetched but no structured price found (site lacks JSON-LD/meta)
  SKIP      listing marked fetch: false

Run it from the Actions tab (workflow_dispatch) to test from GitHub's IPs,
which may be treated differently than your home connection.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from vitasort_pipeline.retailers import base, schema_org, amazon

ADAPTERS = {"amazon": amazon, "schema_org": schema_org}


def main():
    catalog = yaml.safe_load((Path(__file__).parent / "catalog.yaml").read_text())
    counts = {}
    for p in catalog["products"]:
        for listing in p.get("listings", []):
            tag = f"{p['id']} @ {listing['retailer']}"
            if listing.get("fetch") is False:
                status = "SKIP"
            elif listing.get("adapter") == "amazon":
                status = "SKIP (needs PA-API credentials)" if amazon._get_client() is None else _probe(listing)
            elif not base._allowed_by_robots(listing["url"]):
                status = "ROBOTS"
            else:
                status = _probe(listing)
            counts[status.split()[0]] = counts.get(status.split()[0], 0) + 1
            print(f"{status:<8} {tag}")
    print("\nsummary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if not counts.get("OK"):
        print("No working sources. Options: add brand-store listings (most allow "
              "product pages), join retailer affiliate programs for data feeds, "
              "or add Amazon PA-API credentials once approved.")


def _probe(listing) -> str:
    adapter = ADAPTERS[listing["adapter"]]
    resp = base.polite_get(listing["url"])
    if resp is None:
        return "BLOCKED"
    result = adapter.fetch_price(listing) if listing["adapter"] == "amazon" else _extract(resp)
    if not result:
        return "NO-DATA"
    extras = []
    if result.get("rating"):
        extras.append(f"rating {result['rating']['stars']}x{result['rating']['reviews']}")
    if result.get("image"):
        extras.append("image")
    return f"OK       ${result['price']:.2f}" + (f" ({', '.join(extras)})" if extras else "")


def _extract(resp):
    """Run schema_org extraction against an already-fetched response."""
    import json
    for match in schema_org._LDJSON_RE.findall(resp.text):
        try:
            doc = json.loads(match.strip())
        except json.JSONDecodeError:
            continue
        offer = schema_org._extract_offer(doc)
        if offer:
            offer["image"] = schema_org._extract_image(doc)
            offer["rating"] = schema_org._extract_rating(doc)
            return offer
    return None


if __name__ == "__main__":
    main()
