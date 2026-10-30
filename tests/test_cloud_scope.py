import pandas as pd


def test_cloud_scope_uses_only_visible_leaves_and_keeps_unknown_quotes():
    from src.cloud_scope import cloud_scope_summary, cloud_scope_export
    leaves = pd.DataFrame({"个股": ["000001 · 甲", "000002 · 乙"], "涨跌幅": [2, None], "面积": [100, 200]})
    summary = cloud_scope_summary(leaves)
    assert summary == {"样本": 2, "有效涨跌": 1, "上涨": 1, "下跌": 0, "平盘": 0, "平均涨跌": 2.0}
    exported = cloud_scope_export(leaves, date="2026-09-16", area="成交额", color="平均涨跌幅")
    assert exported["代码"].tolist() == ["000001", "000002"]
    assert exported["快照日期"].tolist() == ["2026-09-16"] * 2
    assert exported["面积口径"].tolist() == ["成交额"] * 2
    assert pd.isna(exported.loc[1, "涨跌幅"])


def test_empty_cloud_scope_is_unknown_not_flat_market():
    from src.cloud_scope import cloud_scope_summary
    assert cloud_scope_summary(pd.DataFrame())["平均涨跌"] is None
