"""Derived metrics.

valuePer   — price / total active grams (the headline metric)
valueScore — 0-100, percentile rank of valuePer within its category (lower $ = higher)
score      — VitaScore: 50/50 blend of Bayesian-adjusted rating and valueScore
"""
from statistics import mean

RATING_PRIOR_COUNT = 200  # a product with few reviews is pulled toward the category mean
VALUE_WEIGHT = 0.5
RATING_WEIGHT = 0.5


def value_per(price: float, active_grams_per_serving: float, servings: int) -> float:
    return price / (active_grams_per_serving * servings)


def value_scores(products: list[dict]) -> None:
    """Assign valueScore in-place, percentile-ranked per category (best value = 100)."""
    by_cat: dict[str, list[dict]] = {}
    for p in products:
        by_cat.setdefault(p["cat"], []).append(p)
    for group in by_cat.values():
        ordered = sorted(group, key=lambda p: p["valuePer"])  # cheapest first
        n = len(ordered)
        for i, p in enumerate(ordered):
            p["valueScore"] = 100 if n == 1 else round(100 * (n - 1 - i) / (n - 1))


def bayesian_rating(stars: float, reviews: int, cat_mean: float) -> float:
    return (reviews * stars + RATING_PRIOR_COUNT * cat_mean) / (reviews + RATING_PRIOR_COUNT)


def vita_scores(products: list[dict]) -> None:
    """Assign score (VitaScore) in-place."""
    by_cat: dict[str, list[dict]] = {}
    for p in products:
        by_cat.setdefault(p["cat"], []).append(p)
    for group in by_cat.values():
        cat_mean = mean(p["stars"] for p in group)
        for p in group:
            adj = bayesian_rating(p["stars"], p["reviews"], cat_mean)
            rating_pct = adj / 5 * 100
            p["score"] = round(RATING_WEIGHT * rating_pct + VALUE_WEIGHT * p["valueScore"])
