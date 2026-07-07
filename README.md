# VitaSort

Supplements ranked by **price per gram of active ingredient** — no filler math.
Static frontend + daily price pipeline. Zero servers, effectively $0 to run.

## How it works

```
catalog.yaml (curated facts)          GitHub Actions (daily cron)
        │                                      │
        ▼                                      ▼
pipeline/build.py ──fetch prices──▶ retailer adapters (PA-API / JSON-LD)
        │                                      │
        ▼                                      ▼
   prices.db (history)  ──▶  site/data/products.json  ──▶  GitHub Pages (CDN)
```

The site is **fully static**: the whole catalog ships as one JSON file and all
filtering/sorting happens client-side (PCPartPicker-style instant UI). No live
API means no compute for anyone to abuse — the only attack surface is CDN
bandwidth, which is free at this scale.

Nutrition facts are curated by hand in `pipeline/catalog.yaml` (label scraping
is unreliable); only **prices** update automatically. Same split PCPartPicker
uses.

## Run locally

```bash
pip install -r pipeline/requirements.txt
python3 pipeline/build.py --no-fetch   # export from seed prices (no network)
python3 pipeline/build.py              # fetch live prices first
cd site && python3 -m http.server      # open http://localhost:8000
```

## Deploy (GitHub Pages, free)

1. Push this repo to GitHub.
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. Done. The workflow deploys on push and refreshes prices daily at 09:17 UTC
   (also runnable manually from the Actions tab).

Prefer Cloudflare Pages? Point it at the repo with build output dir `site`
and move the price-fetch step to a scheduled Action that commits `products.json`.

## Retailer adapters

- **`schema_org`** — generic: reads the schema.org Product JSON-LD most
  reputable retailers (iHerb, Myprotein, Shopify stores) embed for SEO.
  Polite by design: respects robots.txt, 1 request / 2 s per host, custom UA.
- **`amazon`** — official PA-API 5. Requires an Amazon Associates account
  (free; links then earn commission). Set repo secrets `AMAZON_ACCESS_KEY`,
  `AMAZON_SECRET_KEY`, `AMAZON_PARTNER_TAG` and uncomment `python-amazon-paapi`
  in `requirements.txt`. Without credentials the adapter is skipped.

A failed fetch never breaks the build: price falls back to the freshest DB
snapshot, then the catalog `seed_price`. **Seed prices are placeholders** —
treat the data as sample until the pipeline has run against live listings.

## Scoring

- `valuePer` = price ÷ (active grams per serving × servings)
  (pre-workout uses $/serving — there's no single active gram there)
- `valueScore` = percentile rank of `valuePer` within its category (0–100)
- `score` (VitaScore) = 50 % Bayesian-adjusted star rating + 50 % valueScore.
  Bayesian prior (200 reviews at category mean) stops a 5.0★ × 3-review
  product outranking a 4.7★ × 8,000-review one. Weights in `scoring.py`.

## Adding a category or product

Categories are pure config — `catalog.yaml → categories` defines the label,
value unit, table columns, dropdown filter, and toggles; the frontend renders
whatever is there. Add a product under `products` with its facts + listings
and rerun the pipeline. `display_cols()`/`specs()` in `build.py` need a case
per category (the only code touch).

## Roadmap (when users show up)

- Price history charts (data is already accumulating in `prices.db`)
- Price-drop alerts (needs accounts/email — first real backend)
- More retailers per product (multi-listing compare is already in the DB layer)
- Server-side rendering for SEO on product pages
