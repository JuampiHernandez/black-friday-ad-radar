#!/usr/bin/env python3
"""Landing page map: where do one advertiser's live ads send people, and what do those pages say?

Steps: list the advertiser's active ads (Firecrawl Alexandria, Upspring ads/browse) -> open each ad (ads/detail) to get
landing_page.url -> group ads by page (host + path, tracking parameters removed) -> read each page with Firecrawl
-> save a dated snapshot -> compare two snapshots (new pages, retired pages, ads moved) -> Firecrawl /monitor (daily by default, --cron to change) on the pages.

  python3 track.py map   ADVERTISER_ID [--ads 25] [--read] [--out snap.json] [--redact]
  python3 track.py diff  OLD.json NEW.json
  python3 track.py map   ADVERTISER_ID --fixtures fixtures     # offline, synthetic, no credits
  python3 track.py monitor URL [URL ...] --webhook https://example.com/hook [--run-now]

Env: FIRECRAWL_API_KEY. No Upspring key is needed: Upspring is reached through Firecrawl Alexandria.
"""
import argparse, json, os, re, sys, urllib.parse, datetime, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import API, http, alexandria, clean

SCHEMA = {"type": "object", "properties": {
    "headline": {"type": ["string", "null"]},
    "price": {"type": ["string", "null"]},
    "offer": {"type": ["string", "null"]},
    "button_label": {"type": ["string", "null"]}}}
PROMPT = "Read the main landing page content only. Return the main headline, the price shown, any discount or offer text, and the label of the main call-to-action button. Use null for anything not on the page."


def page_key(url):
    p = urllib.parse.urlsplit(clean(url))
    host = p.netloc.lower().removeprefix("www.")
    return host + (p.path.rstrip("/") or "/")


def page_type(key):
    path = key.split("/", 1)[1] if "/" in key else ""
    if not path:
        return "home"
    for marker, kind in (("product", "product"), ("collection", "collection"), ("shop", "collection"), ("pages", "landing"), ("lp", "landing"), ("blog", "article")):
        if path.startswith(marker):
            return kind
    return "other"


def list_ads(advertiser_id, n, fixtures=None):
    if fixtures:
        return json.load(open(os.path.join(fixtures, "browse.json")))["data"][:n]
    return alexandria("ads/browse", {"advertiser_id": advertiser_id, "is_active": True, "order_by": "recent", "limit": n})[0]


def open_ad(ad, fixtures=None):
    if fixtures:
        return json.load(open(os.path.join(fixtures, "detail_%s.json" % ad["id"]))), 0
    return alexandria("ads/detail", {"id": ad["id"]})


def read_page(url):
    r = http(API + "/scrape", "POST", {"url": url, "onlyMainContent": True, "formats": [{"type": "json", "schema": SCHEMA, "prompt": PROMPT}]})
    return r["data"].get("json") or {}


def build_map(advertiser_id, n, read=False, fixtures=None):
    ads = list_ads(advertiser_id, n, fixtures)
    pages, credits, failed = {}, 0, 0
    for ad in ads:
        try:
            detail, c = open_ad(ad, fixtures)
        except RuntimeError:
            failed += 1
            continue
        credits += c
        url = (detail.get("landing_page") or {}).get("url")
        if not url:
            failed += 1
            continue
        key = page_key(url)
        page = pages.setdefault(key, {"url": clean(url), "type": page_type(key), "ads": 0, "first_started": None, "last_started": None})
        page["ads"] += 1
        s = detail.get("started_at") or ad.get("started_at")
        if s:
            page["first_started"] = min(filter(None, [page["first_started"], s]))
            page["last_started"] = max(filter(None, [page["last_started"], s]))
    if read and not fixtures:
        for page in pages.values():
            try:
                page["content"] = read_page(page["url"])
            except RuntimeError as e:
                page["content"] = {"_error": str(e)}
    for page in pages.values():
        content = page.get("content")
        if content:
            page["fingerprint"] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:12]
    return {"taken": datetime.date.today().isoformat(), "ads_listed": len(ads), "ads_with_page": len(ads) - failed, "credits": credits, "pages": pages}


def diff(old, new):
    o, n = old["pages"], new["pages"]
    changed = [k for k in o.keys() & n.keys() if o[k].get("fingerprint") and n[k].get("fingerprint") and o[k]["fingerprint"] != n[k]["fingerprint"]]
    moved = {k: n[k]["ads"] - o[k]["ads"] for k in o.keys() & n.keys() if n[k]["ads"] != o[k]["ads"]}
    return {"new_pages": sorted(n.keys() - o.keys()), "retired_pages": sorted(o.keys() - n.keys()), "content_changed": sorted(changed), "ad_count_moved": moved}


def redact(snap):
    out = dict(snap, pages={})
    for i, (key, p) in enumerate(sorted(snap["pages"].items(), key=lambda kv: -kv[1]["ads"]), 1):
        q = {k: v for k, v in p.items() if k not in ("url", "content")}
        q["content_fields_found"] = sum(1 for v in (p.get("content") or {}).values() if v) if p.get("content") else None
        out["pages"]["page-%d" % i] = q
    return out


def monitor(urls, webhook, run_now, cron="0 6 * * *"):
    body = {
        "name": "black-friday-pages",
        "schedule": {"cron": cron, "timezone": "UTC"},
        "goal": "Alert when the headline, price, offer or main button changes. Ignore counters, rotating banners and timestamps.",
        "webhook": {"url": webhook, "events": ["monitor.page", "monitor.check.completed"]},
        "targets": [{"type": "scrape", "urls": [clean(u) for u in urls], "scrapeOptions": {"formats": [{"type": "changeTracking", "modes": ["json"], "schema": SCHEMA, "prompt": PROMPT}]}}],
    }
    m = http(API + "/monitor", "POST", body)["data"]
    out = {"monitor_id": m["id"], "schedule": m["schedule"], "estimatedCreditsPerMonth": m.get("estimatedCreditsPerMonth")}
    if run_now:
        out["check_id"] = http(API + "/monitor/%s/run" % m["id"], "POST")["id"]
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("map"); m.add_argument("advertiser_id"); m.add_argument("--ads", type=int, default=25)
    m.add_argument("--read", action="store_true"); m.add_argument("--out"); m.add_argument("--redact", action="store_true"); m.add_argument("--fixtures")
    d = sub.add_parser("diff"); d.add_argument("old"); d.add_argument("new")
    mo = sub.add_parser("monitor"); mo.add_argument("urls", nargs="+"); mo.add_argument("--webhook", required=True); mo.add_argument("--run-now", action="store_true"); mo.add_argument("--cron", default="0 6 * * *")
    a = ap.parse_args()
    if a.cmd == "map":
        snap = build_map(a.advertiser_id, a.ads, a.read, a.fixtures)
        shown = redact(snap) if a.redact else snap
        text = json.dumps(shown, indent=1)
        if a.out:
            open(a.out, "w").write(json.dumps(snap, indent=1))
        print(text if a.redact else "\n".join("%3d ads  %-10s %s" % (p["ads"], p["type"], k) for k, p in sorted(snap["pages"].items(), key=lambda kv: -kv[1]["ads"])))
        print("ads listed %d, with page %d, distinct pages %d, credits %d" % (snap["ads_listed"], snap["ads_with_page"], len(snap["pages"]), snap["credits"]), file=sys.stderr)
    elif a.cmd == "diff":
        print(json.dumps(diff(json.load(open(a.old)), json.load(open(a.new))), indent=1))
    else:
        print(json.dumps(monitor(a.urls, a.webhook, a.run_now, a.cron), indent=1))


if __name__ == "__main__":
    main()

