import pandas as pd
import pytest
from src.snapshot_review import compare_saved_snapshots


def test_review_compares_matched_stocks_and_respects_replay_cutoff():
    history = pd.DataFrame({"快照日期": ["2026-09-28", "2026-09-28", "2026-09-29", "2026-09-29", "2026-09-30"], "代码": ["1", "2", "1", "3", "1"], "名称": ["甲", "乙", "甲", "丙", "甲"], "价格": [10, 20, 11, 30, 99], "涨跌幅": [1, 2, 3, 4, 9], "成交额": [100, 200, 250, 300, 999]})
    review = compare_saved_snapshots(history, through_date="2026-09-29")
    assert review["current_date"] == "2026-09-29"
    assert review["baseline_date"] == "2026-09-28"
    assert review["added"] == review["removed"] == 1
    stock = review["stocks"].iloc[0]
    assert stock["代码"] == "000001"
    assert stock["价格变化"] == pytest.approx(10)
    assert stock["涨跌幅变化"] == 2
    assert stock["成交额倍数"] == 2.5


def test_review_preserves_unknown_amount_and_invalid_price():
    history = pd.DataFrame({"快照日期": ["2026-09-28", "2026-09-29"], "代码": ["1", "1"], "价格": [0, 11], "成交额": [0, None]})
    stock = compare_saved_snapshots(history)["stocks"].iloc[0]
    assert pd.isna(stock["价格变化"])
    assert pd.isna(stock["成交额倍数"])
    assert pd.isna(stock["涨跌幅变化"])


def test_review_rejects_future_or_same_day_baseline():
    history = pd.DataFrame({"快照日期": ["2026-09-28", "2026-09-29"], "代码": ["1", "1"]})
    assert compare_saved_snapshots(history, baseline_date="2026-09-29")["stocks"].empty
    assert compare_saved_snapshots(history, through_date="2026-09-28")["stocks"].empty
def test_change_distribution_keeps_missing_separate_and_counts_boundaries():
    from src.snapshot_review import snapshot_change_distribution
    import pandas as pd
    result = snapshot_change_distribution(pd.DataFrame({"涨跌幅变化": [-3, -2, -0.5, 0, 0.5, 2, 3, None]}))
    assert result["股票数"].tolist() == [1, 2, 1, 2, 1, 1]
    assert result["区间"].tolist() == ["低于 -2", "-2 至 0（不含0）", "持平", "0 至 2（不含0）", "高于 +2", "缺失"]


def test_industry_review_uses_matched_amount_sample_and_known_changes():
    from src.snapshot_review import industry_snapshot_comparison
    frame = pd.DataFrame({"行业": ["电子", "电子", "电子", "通信"], "涨跌幅变化": [2, -1, None, None],
                          "成交额_当前": [200, None, 300, None], "成交额_对照": [100, 500, 100, None]})
    result = industry_snapshot_comparison(frame).set_index("行业")
    assert result.loc["电子", "共同样本"] == 3
    assert result.loc["电子", "涨幅有效样本"] == 2
    assert result.loc["电子", "平均涨幅变化"] == 0.5
    assert result.loc["电子", "走强比例"] == 50
    assert result.loc["电子", "成交额有效样本"] == 2
    assert result.loc["电子", "成交额倍数"] == 2.5
    assert pd.isna(result.loc["通信", "成交额倍数"])
    assert pd.isna(result.loc["通信", "走强比例"])


def test_industry_review_without_classification_is_empty():
    from src.snapshot_review import industry_snapshot_comparison
    assert industry_snapshot_comparison(pd.DataFrame({"涨跌幅变化": [1]})).empty

