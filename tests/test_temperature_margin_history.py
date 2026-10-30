import pandas as pd
import pytest


def test_margin_history_sums_both_markets_once_and_retains_source_date():
    from src.temperature_margin_history import parse_margin_history
    records = [dict(DIM_DATE='2015-06-18 00:00:00', SCDM='007', RZRQYE=150, RZYE=148, RQYE=2),
               dict(DIM_DATE='2015-06-18 00:00:00', SCDM='001', RZRQYE=80, RZYE=79, RQYE=1)]
    result = parse_margin_history(records, '2015-01-01', '2015-12-31')
    assert result.to_dict() == {'2015-06-18': 230.0}


def test_margin_history_rejects_missing_market_instead_of_partial_sum():
    from src.temperature_margin_history import parse_margin_history
    with pytest.raises(ValueError, match='两市'):
        parse_margin_history([dict(DIM_DATE='2015-06-18', SCDM='007', RZRQYE=150, RZYE=148, RQYE=2)],
                             '2015-01-01', '2015-12-31')


def test_margin_history_rejects_duplicate_market_rows():
    from src.temperature_margin_history import parse_margin_history
    record = dict(DIM_DATE='2015-06-18', SCDM='007', RZRQYE=150, RZYE=148, RQYE=2)
    with pytest.raises(ValueError, match='重复'):
        parse_margin_history([record, record], '2015-01-01', '2015-12-31')


def test_margin_history_rejects_component_mismatch():
    from src.temperature_margin_history import parse_margin_history
    with pytest.raises(ValueError, match='分量'):
        parse_margin_history([dict(DIM_DATE='2015-06-18', SCDM='007', RZRQYE=150, RZYE=100, RQYE=2)],
                             '2015-01-01', '2015-12-31')
