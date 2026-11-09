# Black Friday ad and landing page radar

Companion code for the guide "Track Black Friday ads and landing pages with Upspring and Firecrawl Alexandria". It finds live Black Friday ads with Upspring data in Firecrawl Alexandria, looks up Shopify prices, reads each landing page, and sets up a Firecrawl /monitor.
Python 3.9 or newer, standard library only. You need a Firecrawl API key (FIRECRAWL_API_KEY). No Upspring or Shopify account is needed: both are reached through Firecrawl Alexandria.

    python3 -m unittest -v                          # offline tests, no credits
    python3 radar.py x --fixtures fixtures --redact  # offline digest on invented data
    python3 radar.py apparel --query "black friday" --country US --open 8 --redact
    python3 track.py monitor PAGE_URL [PAGE_URL ...] --webhook https://example.com/hooks/firecrawl --cron "0 6 * * *"

A live run with eight opened ads uses about 955 Firecrawl credits for the Alexandria calls plus the page reads. Use --open 3 for a cheaper run.
Without --redact the digest prints real advertiser names, page addresses and screenshot links: keep it private.
The fixtures contain invented data on example domains.
