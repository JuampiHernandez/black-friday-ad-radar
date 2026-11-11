import os, unittest
import radar

FX = os.path.join(os.path.dirname(__file__), "fixtures")


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.r = radar.build("example_vertical", "black friday", "US", 3, 14, fixtures=FX)

    def test_country_filter_keeps_us_ads_and_counts_all_countries(self):
        self.assertEqual((self.r["searched"], self.r["kept"]), (7, 5))
        self.assertEqual(self.r["countries"]["US"], 5)
        self.assertEqual(self.r["countries"]["BR"], 1)

    def test_all_keeps_every_country(self):
        r = radar.build("example_vertical", "black friday", "ALL", 0, 14, fixtures=FX)
        self.assertEqual(r["kept"], 7)

    def test_ads_without_a_score_are_skipped(self):
        self.assertEqual(self.r["scored"], 4)

    def test_offer_lift_ranks_bundle_first(self):
        self.assertEqual(self.r["offers"][0]["type"], "Bundle")
        self.assertAlmostEqual(self.r["offers"][0]["lift"], 3.0)

    def test_two_ads_one_page_and_missing_page_counted(self):
        r = radar.build("example_vertical", "black friday", "US", 4, 14, fixtures=FX)
        self.assertEqual(r["opened"], 4)
        self.assertEqual(sorted(r["pages"]), ["shop1.example.com/products/trail-runner", "shop2.example.com/collections/sale"])
        self.assertEqual(r["pages"]["shop2.example.com/collections/sale"]["ads"], 2)

    def test_each_advertiser_is_opened_once_before_a_second_ad_from_the_same_one(self):
        self.assertEqual((self.r["opened"], self.r["no_page"]), (3, 1))
        self.assertEqual(self.r["pages"]["shop2.example.com/collections/sale"]["ads"], 1)

    def test_catalog_price_and_was_price_attached_to_product_page_only(self):
        p = self.r["pages"]
        self.assertEqual(p["shop1.example.com/products/trail-runner"]["catalog"]["was"], 100.0)
        self.assertIsNone(p["shop2.example.com/collections/sale"]["catalog"])
        self.assertIn("21% off", radar.digest(self.r))

    def test_redacted_digest_has_no_names_or_hosts(self):
        text = radar.digest(self.r, redact=True)
        self.assertNotIn("example", text.replace("example_vertical", "").lower())
        self.assertIn("advertiser 1", text)

    def test_digest_has_no_em_dash(self):
        self.assertNotIn(chr(8212), radar.digest(self.r))


if __name__ == "__main__":
    unittest.main()
