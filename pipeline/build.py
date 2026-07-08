#!/usr/bin/env python3
"""VitaSort pipeline: catalog + live prices -> site/data/products.json

  python3 build.py                # fetch live prices, then export
  python3 build.py --no-fetch     # export from DB/seed prices only

Price resolution per product: freshest DB snapshot (lowest across retailers)
-> catalog seed_price. A fetch failure never breaks the build.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from vitasort_pipeline import db, scoring
from vitasort_pipeline.retailers import amazon, schema_org

ROOT = Path(__file__).resolve().parent.parent
CATALOG = Path(__file__).parent / "catalog.yaml"
DB_PATH = Path(__file__).parent / "prices.db"
OUT = ROOT / "site" / "data" / "products.json"

ADAPTERS = {"amazon": amazon, "schema_org": schema_org}


def caffeine_bucket(mg: int) -> str:
    return "Under 200 mg" if mg < 200 else "200–300 mg" if mg <= 300 else "300+ mg"


def display_cols(p: dict) -> list[str]:
    a = p["attrs"]
    c = p["cat"]
    if c == "protein":
        return [a["source"], "Complete" if a.get("complete") else "—", f"{a['proteinServ']} g"]
    if c == "creatine":
        return [a["form"], "Micronized" if a.get("micronized") else "—", f"{a['dose']} g"]
    if c == "preworkout":
        return [f"{a['caffeineMg']} mg", a["form"], str(p["servings"])]
    if c == "omega3":
        return [a["form"], f"{a['epaDhaMg']} mg", str(p["servings"])]
    return ["—", "—", "—"]


def specs(p: dict, cat_cfg: dict) -> list[list[str]]:
    a = p["attrs"]
    rows = [["Brand", p["brand"]], ["Servings per container", str(p["servings"])]]
    labels = {
        "source": "Protein source", "complete": "Complete protein",
        "proteinServ": "Protein per serving", "form": "Form",
        "micronized": "Micronized", "dose": "Dose per serving",
        "caffeineMg": "Caffeine per serving", "stimFree": "Stim-free",
        "epaDhaMg": "EPA + DHA per serving",
    }
    units = {"proteinServ": " g", "dose": " g", "caffeineMg": " mg", "epaDhaMg": " mg"}
    for k, v in a.items():
        if k in ("caffeineBucket",) or k not in labels:
            continue
        if isinstance(v, bool):
            v = "Yes" if v else "No"
        rows.append([labels[k], f"{v}{units.get(k, '')}"])
    rows.append(["Price", f"${p['price']:.2f}"])
    rows.append(["Price per serving", f"${p['price'] / p['servings']:.2f}"])
    unit = cat_cfg["valueHeader"].replace("$/", "Cost per ")
    rows.append([unit, f"${p['valuePer']:.{cat_cfg['valueDecimals']}f}"])
    return rows


def fetch_prices(catalog: dict, conn) -> None:
    for p in catalog["products"]:
        for listing in p.get("listings", []):
            adapter = ADAPTERS.get(listing.get("adapter"))
            if adapter is None:
                print(f"  unknown adapter {listing.get('adapter')!r} on {p['id']}")
                continue
            print(f"fetching {p['id']} @ {listing['retailer']}")
            result = adapter.fetch_price(listing)
            if result:
                db.record_price(conn, p["id"], listing["retailer"],
                                result["price"], result["in_stock"],
                                result.get("url") or listing.get("url"))
                if result.get("image"):
                    db.record_image(conn, p["id"], result["image"])
                print(f"  ${result['price']:.2f} ({'in stock' if result['in_stock'] else 'OOS'})")


def export(catalog: dict, conn) -> None:
    products = []
    for src in catalog["products"]:
        p = dict(src)
        listings = p.get("listings") or []
        first_listing = (listings or [{}])[0]
        live_offers = db.all_latest(conn, p["id"])
        seen = {o["retailer"] for o in live_offers}
        # listings without a live snapshot still appear as link-only offers
        offers = live_offers + [
            {"retailer": l["retailer"], "price": None, "in_stock": True, "url": l.get("url")}
            for l in listings if l["retailer"] not in seen
        ]
        priced = sorted([o for o in offers if o["price"] is not None],
                        key=lambda o: (not o["in_stock"], o["price"]))
        if priced:
            best = priced[0]
            p.update(price=best["price"], retailer=best["retailer"],
                     stock=best["in_stock"], url=best["url"] or first_listing.get("url"))
        else:
            p.update(price=p["seed_price"], retailer=first_listing.get("retailer", "—"),
                     stock=True, url=first_listing.get("url"))
            if offers:
                offers[0] = {**offers[0], "price": p["seed_price"]}
        p["offers"] = priced + [o for o in offers if o["price"] is None] if priced else offers
        p["image"] = src.get("image") or db.latest_image(conn, p["id"])
        tag = os.environ.get("AMAZON_PARTNER_TAG")
        if tag and p["retailer"] == "Amazon" and p.get("url") and "tag=" not in p["url"]:
            p["url"] += ("&" if "?" in p["url"] else "?") + "tag=" + tag
        if p["cat"] == "preworkout":
            p["attrs"]["caffeineBucket"] = caffeine_bucket(p["attrs"]["caffeineMg"])
        p["valuePer"] = scoring.value_per(p["price"], p["active_grams_per_serving"], p["servings"])
        products.append(p)

    scoring.value_scores(products)
    scoring.vita_scores(products)

    out_products = []
    for p in products:
        cat_cfg = catalog["categories"][p["cat"]]
        out_products.append({
            "id": p["id"], "cat": p["cat"], "name": p["name"], "brand": p["brand"],
            "price": round(p["price"], 2), "servings": p["servings"],
            "retailer": p["retailer"], "url": p.get("url"), "stock": p["stock"],
            "image": p.get("image"), "offers": p["offers"],
            "stars": p["stars"], "reviews": p["reviews"],
            "valuePer": round(p["valuePer"], 4), "valueScore": p["valueScore"], "score": p["score"],
            "attrs": p["attrs"], "cols": display_cols(p), "specs": specs(p, cat_cfg),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "categories": catalog["categories"],
        "products": out_products,
    }, indent=1))
    with_img = sum(1 for p in out_products if p["image"])
    print(f"wrote {OUT} ({len(out_products)} products, {with_img} with images)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="skip live price fetching")
    args = ap.parse_args()

    catalog = yaml.safe_load(CATALOG.read_text())
    conn = db.connect(DB_PATH)
    if not args.no_fetch:
        fetch_prices(catalog, conn)
    export(catalog, conn)


if __name__ == "__main__":
    main()
