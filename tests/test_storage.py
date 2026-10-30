from src.models import TradePlan
from src.models import TradeRecord
from src.storage import save_trade_record, list_trade_records
from src.storage import save_theme_snapshot, list_theme_snapshots
from src.storage import save_trade_plan, list_trade_plans, save_portfolio_snapshot, list_portfolio_snapshots, save_market_snapshot, list_market_snapshots
from src.calculations import market_breadth_metrics
import pandas as pd


def test_trade_plan_round_trip(tmp_path):
    path = str(tmp_path / "decision.db")
    plan = TradePlan("2026-09-16", "688008", "澜起科技", "中线", "趋势修复", "跌破20日线", .2, 180, 260)
    assert save_trade_plan(path, plan) == 1
    assert list_trade_plans(path)[0].code == "688008"


def test_portfolio_snapshot_round_trip(tmp_path):
    path = str(tmp_path / "decision.db")
    values = [{"slot": "attack1", "amount": 120000.0}, {"slot": "defense1", "amount": 80000.0}]
    assert save_portfolio_snapshot(path, "2026-09-16", values) == 1
    saved = list_portfolio_snapshots(path)
    assert saved[0]["trade_date"] == "2026-09-16"
    assert saved[0]["positions"][0]["amount"] == 120000.0


def test_market_snapshot_upserts_per_day_and_lists_newest_first(tmp_path):
    path = str(tmp_path / "decision.db")
    save_market_snapshot(path, "2026-09-15", {"score": 2, "stage": "震荡"})
    save_market_snapshot(path, "2026-09-16", {"score": 4, "stage": "修复"})
    save_market_snapshot(path, "2026-09-15", {"score": 3, "stage": "修复"})
    snapshots = list_market_snapshots(path)
    assert len(snapshots) == 2
    assert snapshots[0]["trade_date"] == "2026-09-16"
    assert snapshots[1]["score"] == 3


def test_market_breadth_ignores_missing_and_non_numeric_rows():
    metrics = market_breadth_metrics(pd.DataFrame({"涨跌幅": [1.2, -0.5, 0, None, "停牌"], "成交额": [10, 20, 30, None, 40]}))
    assert metrics["valid"] == 3
    assert (metrics["up"], metrics["down"], metrics["flat"]) == (1, 1, 1)
    assert metrics["amount_sum"] == 100
    assert metrics["advance_ratio"] == 1 / 3
    assert metrics["breadth_read"] == "mixed"


def test_market_breadth_flags_clear_advancing_or_declining_tape():
    advancing = market_breadth_metrics(pd.DataFrame({"涨跌幅": [1, 2, 0, None]}))
    declining = market_breadth_metrics(pd.DataFrame({"涨跌幅": [-1, -2, 0]}))
    assert advancing["breadth_read"] == "broad_advance"
    assert declining["breadth_read"] == "broad_decline"
def test_trade_records_round_trip(tmp_path):
    path = str(tmp_path / "records.db")
    save_trade_record(path, TradeRecord("2026-09-18", "000001", "测试", "买入", 10.5, 100, 2.0, "首笔"))
    rows = list_trade_records(path)
    assert rows[0].code == "000001"
    assert rows[0].quantity == 100


def test_theme_snapshot_round_trip(tmp_path):
    path = str(tmp_path / "theme.db")
    save_theme_snapshot(path, "2026-09-18", "CPO", {"count": 3, "average_change": 1.2, "codes": ["300308"]})
    rows = list_theme_snapshots(path)
    assert rows[0]["theme"] == "CPO"
    assert rows[0]["count"] == 3
