import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src import stock_intraday


class StockIntradayTests(unittest.TestCase):
    def test_failed_fetch_is_throttled_across_reruns(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(stock_intraday, "_CACHE_DIR", Path(directory)):
                with patch.object(stock_intraday, "_fetch_minutes", side_effect=RuntimeError("源暂不可用")) as fetch:
                    first, _, first_error = stock_intraday.load_stock_minutes("000001")
                    second, _, second_error = stock_intraday.load_stock_minutes("000001")
            self.assertTrue(first.empty)
            self.assertTrue(second.empty)
            self.assertEqual(fetch.call_count, 1)
            self.assertIn("源暂不可用", first_error)
            self.assertIn("源暂不可用", second_error)

    def test_normalize_keeps_trading_minutes_and_real_prices(self):
        frame = pd.DataFrame([
            {"时间": "2026-10-16 09:29:00", "收盘": 10, "成交量": 1},
            {"时间": "2026-10-16 09:30:00", "收盘": 11, "成交量": 2},
            {"时间": "2026-10-16 12:00:00", "收盘": 12, "成交量": 3},
            {"时间": "2026-10-16 13:00:00", "收盘": 13, "成交量": 4},
        ])
        result = stock_intraday._normalize(frame)
        self.assertEqual(result["收盘"].tolist(), [11, 13])


if __name__ == "__main__":
    unittest.main()
