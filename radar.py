#!/usr/bin/env python3
"""Black Friday ad and landing page radar for one category.

Steps (all data calls go through Firecrawl Alexandria):
  1. Upspring ads/search: live ads that mention your keyword, with advertiser and countries
  2. keep ads shown in your country, take the strongest by impressions score
  3. Upspring ads/breakdown: which offer types are over-represented this week
  4. Upspring ads/detail: the landing page of each strong ad
  5. Shopify catalog/lookup_catalog: price and was-price for the product pages that are on Shopify (one call)
  6. Firecrawl scrape: headline, offer text, button and a screenshot of each page
  7. one markdown digest; then watch the pages with track.py monitor (Firecrawl /monitor)

  python3 radar.py CATEGORY [--query "black friday"] [--country US] [--open 8] [--days 14] [--no-pages] [--redact] [--out digest.md]
  python3 radar.py x --fixtures fixtures --redact     # offline, synthetic, no credits

Env: FIRECRAWL_API_KEY. Pass --country ALL to keep ads from every country.
"""
import argparse, collections, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import API, http, alexandria, clean
from track import page_key, page_type, SCHEMA, PROMPT


def get(capability, options, fixtures, name, provider="upspring"):
    if fixtures:
        return json.load(open(os.path.join(fixtures, name + ".json"))), 0
    return alexandria(capability, options, provider)


def scrape_page(url):
    r = http(API + "/scrape", "POST", {"url": url, "onlyMainContent": True, "formats": [{"type": "json", "schema": SCHEMA, "prompt": PROMPT}, "screenshot"]})["data"]
    return r.get("json") or {}, r.get("screenshot"), (r.get("metadata") or {}).get("url") or url


def offer_lift(week, everything):
    base = {r["id"]: r["share"] for r in everything}
    rows = [{"type": r["label"], "week_share": r["share"], "all_share": base.get(r["id"], 0), "lift": r["share"] / base[r["id"]] if base.get(r["id"]) else None} for r in week]
    return sorted([r for r in rows if r["lift"]], key=lambda r: -r["lift"])


def price_by_page(urls, fixtures):
    """Shopify catalog lookup for many product URLs in one call. Returns {page_key: {price, was}} for the pages Shopify knows."""
    if not urls:
        return {}, 0
    data, credits = get("catalog/lookup_catalog", {"product_ids": urls}, fixtures, "lookup", "shopify")
    found = {}
    for product in data.get("products", []):
        variant = (product.get("variants") or [{}])[0]
        if not variant.get("url"):
            continue
        price, was = (variant.get("price") or {}).get("amount"), (variant.get("list_price") or {}).get("amount")
        found[page_key(variant["url"])] = {"price": price / 100.0 if price else None, "was": was / 100.0 if was else None,
                                           "currency": (variant.get("price") or {}).get("currency"), "available": (variant.get("availability") or {}).get("available")}
    return found, credits


def build(category, query, country, n_open, days, pages=True, fixtures=None):
    credits = 0
    scope = {"vertical": category, "recency_days": days, "is_active": True}
    found, c = get("ads/search", dict(scope, q=query, limit=50), fixtures, "search"); credits += c
    countries = collections.Counter(x for ad in found for x in (ad.get("countries") or ["unknown"]))
    kept = [ad for ad in found if country == "ALL" or country in (ad.get("countries") or [])]
    scored = sorted([ad for ad in kept if (ad.get("strength") or {}).get("impressions")], key=lambda ad: (ad["strength"]["impressions"], ad["started_at"]), reverse=True)
    week, c = get("ads/breakdown", {"group_by": "offer_type", "vertical": category, "recency_days": 7}, fixtures, "breakdown_week"); credits += c
    everything, c = get("ads/breakdown", {"group_by": "offer_type", "vertical": category}, fixtures, "breakdown_all"); credits += c
    out = {"category": category, "query": query, "country": country, "days": days, "searched": len(found), "countries": dict(countries.most_common()), "kept": len(kept),
           "advertisers": len({(ad.get("advertiser") or {}).get("id") for ad in kept}), "scored": len(scored), "offers": offer_lift(week, everything)[:3], "opened": 0, "pages": {}, "no_page": 0}
    for ad in scored[:n_open]:
        try:
            detail, c = get("ads/detail", {"id": ad["id"]}, fixtures, "detail_%s" % ad["id"]); credits += c
        except RuntimeError:
            out["no_page"] += 1
            continue
        out["opened"] += 1
        url = (detail.get("landing_page") or {}).get("url")
        if not url:
            out["no_page"] += 1
            continue
        key = page_key(url)
        page = out["pages"].setdefault(key, {"url": clean(url), "type": page_type(key), "ads": 0, "advertiser": (ad.get("advertiser") or {}).get("name"), "offer_on_ad": (detail.get("offer") or {}).get("text")})
        page["ads"] += 1
    prices, c = price_by_page([p["url"] for p in out["pages"].values() if p["type"] == "product"], fixtures); credits += c
    for key, page in out["pages"].items():
        page["catalog"] = prices.get(key)
    if pages and not fixtures:
        for page in out["pages"].values():
            try:
                page["content"], page["screenshot"], page["final_url"] = scrape_page(page["url"])
            except RuntimeError as e:
                page["content"], page["screenshot"], page["final_url"] = {"_error": str(e)}, None, page["url"]
    out["credits"] = credits
    return out


def money(p):
    return "%s %.2f" % (p.get("currency") or "", p["price"]) if p and p.get("price") else "none"


def digest(r, redact=False):
    lines = ["# Radar: %s, last %d days" % ("category" if redact else r["category"], r["days"]), "",
             "%d ads found for the keyword, %d shown in %s, from %d advertisers. Ads by country: %s." % (r["searched"], r["kept"], r["country"], r["advertisers"], ", ".join("%s %d" % kv for kv in r["countries"].items())), "",
             "## Offer types over-represented this week"]
    lines += ["- %s: %.0f%% of this week's strongest ads against %.0f%% of the strongest ads overall (%.1fx)" % (o["type"], 100 * o["week_share"], 100 * o["all_share"], o["lift"]) for o in r["offers"]]
    lines += ["", "## Pages behind the strongest ads (%d opened, %d without a page)" % (r["opened"], r["no_page"])]
    for i, (key, p) in enumerate(sorted(r["pages"].items(), key=lambda kv: -kv[1]["ads"]), 1):
        content, cat = p.get("content") or {}, p.get("catalog")
        name = "advertiser %d" % i if redact else p["advertiser"]
        where = "[page %d, %s]" % (i, p["type"]) if redact else key
        lines.append("- %s, %s, %d strong ad(s)" % (name, where, p["ads"]))
        if cat and cat.get("was"):
            lines.append("  catalog: %s, was %.2f, %.0f%% off, in stock: %s" % (money(cat), cat["was"], 100 * (1 - cat["price"] / cat["was"]), cat.get("available")))
        elif cat:
            lines.append("  catalog: %s, no was-price, in stock: %s" % (money(cat), cat.get("available")))
        else:
            lines.append("  catalog: not a Shopify product page")
        if redact:
            found = [k for k in ("headline", "price", "offer", "button_label") if content.get(k)]
            lines.append("  page fields read: %s; screenshot: %s" % (", ".join(found) or "none", "yes" if p.get("screenshot") else "no"))
        else:
            lines.append("  page: headline %s | price %s | offer %s | button %s" % tuple(content.get(k) or "none" for k in ("headline", "price", "offer", "button_label")))
            lines.append("  screenshot: %s" % (p.get("screenshot") or "none"))
    lines += ["", "Cost: %d Firecrawl credits for the Alexandria calls, plus the page reads. Offer labels are Upspring's estimates of the creative." % r["credits"]]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("category"); ap.add_argument("--query", default="black friday"); ap.add_argument("--country", default="US")
    ap.add_argument("--open", type=int, default=8); ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--no-pages", action="store_true"); ap.add_argument("--redact", action="store_true"); ap.add_argument("--out"); ap.add_argument("--fixtures")
    a = ap.parse_args()
    r = build(a.category, a.query, a.country.upper(), a.open, a.days, not a.no_pages, a.fixtures)
    text = digest(r, a.redact)
    if a.out:
        open(a.out, "w").write(text)
    print(text)
    print(json.dumps({k: r[k] for k in ("searched", "kept", "scored", "opened", "no_page", "credits")}), file=sys.stderr)


if __name__ == "__main__":
    main()
