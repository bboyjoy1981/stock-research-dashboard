import pandas as pd


def test_closing_report_preserves_snapshot_date_source_and_missing_quotes():
    from src.closing_report import closing_report
    result = closing_report({'stocks':pd.DataFrame({'涨跌幅':[2,-1,0,None], '成交额':[100,None,0,50]}),
                             'import_date':'2026-09-16','stock_quote_source':'imported'}, pd.DataFrame(), '行业')
    assert '2026-09-16' in result
    assert '导入快照' in result
    assert '上涨 1 / 下跌 1 / 平盘 1 / 未知 1' in result
    assert '有效成交额 150.00 元' in result
    assert '覆盖 3/4' in result


def test_closing_report_does_not_invent_missing_amount_or_sector():
    from src.closing_report import closing_report
    result = closing_report({'stocks':pd.DataFrame({'涨跌幅':[None]}),
                             'stock_quote_source':'demo'}, pd.DataFrame(), '行业')
    assert '演示数据' in result
    assert '成交额未提供' in result
    assert '暂无可比较的行业样本' in result
    assert '平均涨跌 —' in result
