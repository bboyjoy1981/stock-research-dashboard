import unittest

import pandas as pd

from src.cyber_desk_model import build_cyber_desk_model


class CyberDeskModelTests(unittest.TestCase):
    def test_no_imported_watchlist_is_empty_even_when_demo_stocks_exist(self):
        model = build_cyber_desk_model({"stocks": pd.DataFrame([{"代码": "000001", "名称": "演示股票"}])})
        self.assertEqual(model["mode"], "empty")
        self.assertEqual(model["stocks"], [])

    def test_quotes_require_imported_snapshot_and_keep_missing_values_missing(self):
        pool = pd.DataFrame([
            {"代码": "000001", "名称": "关注甲", "板块": "半导体"},
            {"代码": "000002", "名称": "关注乙", "板块": "机器人"},
        ])
        quotes = pd.DataFrame([{"代码": "000001", "价格": 12.5, "涨跌幅": 2.4}])
        model = build_cyber_desk_model({
            "research_pool": pool, "stocks": quotes,
            "watchlist_codes": ["000001", "000002"],
            "stock_quote_source": "imported", "import_date": "2026-10-15",
        })
        self.assertEqual(model["mode"], "snapshot")
        self.assertEqual(model["snapshot_date"], "2026-10-15")
        self.assertEqual(model["stocks"][0]["change_pct"], 2.4)
        self.assertIsNone(model["stocks"][1]["change_pct"])
        self.assertIsNone(model["stocks"][1]["price"])

    def test_demo_quote_source_never_exposes_demo_prices_as_watchlist_quotes(self):
        pool = pd.DataFrame([{"代码": "000001", "名称": "关注甲"}])
        demo = pd.DataFrame([{"代码": "000001", "价格": 20, "涨跌幅": 10}])
        model = build_cyber_desk_model({"research_pool": pool, "stocks": demo, "stock_quote_source": "demo", "watchlist_codes": ["000001"]})
        self.assertEqual(model["mode"], "watchlist_only")
        self.assertIsNone(model["stocks"][0]["price"])

    def test_missing_sector_fields_do_not_become_nan_label(self):
        pool = pd.DataFrame([{"代码": "000001", "名称": "关注甲", "细分行业": float("nan"), "板块": "半导体"}])
        model = build_cyber_desk_model({"research_pool": pool, "watchlist_codes": ["000001"]})
        self.assertEqual(model["stocks"][0]["sector"], "半导体")

    def test_full_market_import_is_not_implicitly_my_watchlist(self):
        pool = pd.DataFrame([{"代码": "000001", "名称": "全市场股票"}])
        model = build_cyber_desk_model({"research_pool": pool, "watchlist_codes": []})
        self.assertEqual(model["mode"], "empty")
        self.assertEqual(model["stocks"], [])


if __name__ == "__main__":
    unittest.main()
