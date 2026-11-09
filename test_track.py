import json, os, unittest
import track

FX = os.path.join(os.path.dirname(__file__), "fixtures")


class TrackTests(unittest.TestCase):
    def test_page_key_drops_tracking_www_and_fragment(self):
        self.assertEqual(track.page_key("https://www.shoes.example.com/products/a/?utm_source=x&fbclid=1#top"), "shoes.example.com/products/a")
        self.assertEqual(track.page_key("https://shoes.example.com"), "shoes.example.com/")

    def test_page_type(self):
        self.assertEqual(track.page_type("shoes.example.com/products/a"), "product")
        self.assertEqual(track.page_type("shoes.example.com/collections/sale"), "collection")
        self.assertEqual(track.page_type("shoes.example.com/"), "home")
        self.assertEqual(track.page_type("shoes.example.com/about"), "other")

    def test_map_groups_ads_by_page(self):
        snap = track.build_map("adv-1", 10, fixtures=FX)
        self.assertEqual(snap["ads_listed"], 6)
        self.assertEqual(snap["ads_with_page"], 5)
        self.assertEqual(len(snap["pages"]), 4)
        self.assertEqual(snap["pages"]["shoes.example.com/products/trail-runner"]["ads"], 2)
        self.assertEqual(snap["pages"]["shoes.example.com/products/trail-runner"]["first_started"], "2026-10-01")

    def test_diff_finds_new_retired_changed_and_moved(self):
        old = json.load(open(os.path.join(FX, "snap_old.json")))
        new = json.load(open(os.path.join(FX, "snap_new.json")))
        d = track.diff(old, new)
        self.assertEqual(d["new_pages"], ["shoes.example.com/products/road-racer"])
        self.assertEqual(d["retired_pages"], ["shoes.example.com/products/old-model"])
        self.assertEqual(d["content_changed"], ["shoes.example.com/collections/sale"])
        self.assertEqual(d["ad_count_moved"], {"shoes.example.com/products/trail-runner": 1})

    def test_redact_removes_urls_and_hosts(self):
        text = json.dumps(track.redact(track.build_map("adv-1", 10, fixtures=FX)))
        self.assertNotIn("example.com", text)
        self.assertIn("page-1", text)


if __name__ == "__main__":
    unittest.main()
