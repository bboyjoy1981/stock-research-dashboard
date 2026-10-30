import pandas as pd


def test_confirmed_limits_use_prices_not_nine_point_eight_threshold():
    from src.price_limits import confirmed_limit_counts
    stocks = pd.DataFrame({'代码': ['600001', '300001', '600002', '600003'],
                           '价格': [11, 11, 9.5, 10], '涨停价': [11, 12, 10.5, None],
                           '跌停价': [9, 8, 9.5, None], '涨跌幅': [10, 10, -5, 0]})
    assert confirmed_limit_counts(stocks) == {'up': 1, 'down': 1, 'covered': 3, 'total': 4}


def test_missing_limits_are_unknown_not_zero():
    from src.price_limits import confirmed_limit_counts
    result = confirmed_limit_counts(pd.DataFrame({'代码': ['001246'], '价格': [65], '涨跌幅': [206]}))
    assert result == {'up': None, 'down': None, 'covered': 0, 'total': 1}


def test_duplicate_stocks_and_invalid_limit_values_do_not_inflate_counts():
    from src.price_limits import confirmed_limit_counts
    result = confirmed_limit_counts(pd.DataFrame({'代码': ['600001', '600001', '600002'],
        '价格': [11, 11, 10], '涨停价': [11, 11, 0], '跌停价': [9, 9, 0]}))
    assert result == {'up': 1, 'down': 0, 'covered': 1, 'total': 2}
