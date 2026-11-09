import json, os, sys, time, urllib.error, urllib.parse, urllib.request, uuid

API = "https://api.firecrawl.dev/v2"
TRACKING = ("utm_", "fbclid", "gclid", "ttclid", "msclkid", "mc_", "_hs", "_gsid", "variant")


def http(url, method="GET", body=None, headers=None, retries=4):
    if not os.environ.get("FIRECRAWL_API_KEY"):
        sys.exit("Set FIRECRAWL_API_KEY first (a Firecrawl API key; no provider keys are needed).")
    h = {"Authorization": "Bearer " + os.environ["FIRECRAWL_API_KEY"], "x-request-id": str(uuid.uuid4()), **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method), timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < retries:
                time.sleep(min(float(e.headers.get("Retry-After") or 2 ** (attempt + 1)), 30))
                continue
            raise RuntimeError("HTTP %s from %s" % (e.code, urllib.parse.urlsplit(url).path))


def alexandria(capability, options, provider="upspring"):
    """One Firecrawl Alexandria call. Upspring wants every option value as a string; Shopify wants real numbers and lists."""
    if provider == "upspring":
        options = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in options.items()}
    item = http(API + "/scrape", "POST", {"alexandria": {"provider": provider, "capability": capability, "options": options}})["data"]["alexandria"][0]
    if item.get("error"):
        raise RuntimeError("alexandria error: %s" % item["error"])
    inner = item["data"]
    return inner.get("data", inner), item.get("creditsCost", 0)


def clean(url):
    p = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(TRACKING)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))
