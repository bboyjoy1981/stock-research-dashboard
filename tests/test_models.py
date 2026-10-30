from src.models import MarketSnapshot, StockRow


def test_market_snapshot_has_required_fields():
    row = MarketSnapshot("沪深300", 4609.18, -0.46, 1)
    assert row.name == "沪深300"
    assert row.score == 1


def test_stock_row_can_hold_research_fields():
    row = StockRow("688008", "澜起科技", "存储/半导体", 216.38, -1.2, 82, 38)
    assert row.code == "688008"
    assert row.risk_score == 38
