import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest
import pandas as pd

from src.watchlist_store import load_watchlist


class CyberDeskUiTests(unittest.TestCase):
    def test_monitor_uses_observed_history_only(self):
        from src.cyber_desk import _sparkline

        self.assertIn("暂无历史轨迹", _sparkline(None, "000001", "2026-10-15"))
        history = pd.DataFrame([
            {"快照日期": "2026-10-14", "代码": "000001", "价格": 10},
            {"快照日期": "2026-10-15", "代码": "000001", "价格": 12},
        ])
        graph = _sparkline(history, "000001", "2026-10-15")
        self.assertEqual(graph.count("--bar-height:"), 2)
        self.assertIn("导入历史快照价格轨迹", graph)

    def test_add_and_remove_watchlist_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watchlist.json"
            script = f'''
from pathlib import Path
import pandas as pd
import src.cyber_desk as desk
desk._WATCHLIST_PATH = Path({str(path)!r})
data = {{
    "research_pool": pd.DataFrame([{{"代码": "000001", "名称": "关注甲", "板块": "半导体"}}, {{"代码": "000002", "名称": "关注乙", "板块": "半导体"}}]),
    "stocks": pd.DataFrame([{{"代码": "000001", "价格": 12.5, "涨跌幅": 2.4}}, {{"代码": "000002", "价格": 11, "涨跌幅": -1}}]),
    "stock_quote_source": "imported",
    "import_date": "2026-10-15",
}}
desk.render_cyber_desk(data)
'''
            app = AppTest.from_string(script, default_timeout=10).run()
            self.assertFalse(app.exception)
            app.selectbox(key="cyber_add_stock").select("关注甲 · 000001").run()
            self.assertFalse(app.exception)
            app.button(key="cyber_add_button").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(load_watchlist(path), ["000001"])
            self.assertFalse(any("关联板块" in item.value for item in app.subheader))
            self.assertFalse(any("导入快照价格轨迹" in item.value for item in app.subheader))
            app.selectbox(key="cyber_add_stock").select("关注乙 · 000002").run()
            app.button(key="cyber_add_button").click().run()
            self.assertEqual(load_watchlist(path), ["000001", "000002"])
            app.selectbox(key="cyber_focus_stock").select("000002").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["cyber_focus_stock"], "000002")
            app.button(key="cyber_remove_000001").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(load_watchlist(path), ["000002"])
            app.button(key="cyber_remove_000002").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(load_watchlist(path), [])


if __name__ == "__main__":
    unittest.main()
