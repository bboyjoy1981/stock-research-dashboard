import pandas as pd
import pytest

from src import overseas_temperature as overseas


def test_csv_excludes_unfinished_session_and_retains_null_holiday_gap():
    text = 'observation_date,SP500\n2026-09-25,100\n2026-09-28,.\n2026-09-29,102\n2026-09-30,105\n'
    cutoff = pd.Timestamp('2026-09-30T15:00:00+08:00')
    result = overseas.parse_daily_csv(text, 'sp500', cutoff)
    assert result['data_period'].tolist() == ['2026-09-25', '2026-09-29']
    assert result['value'].tolist() == [100, 102]
    # Unknown historical publication is not backdated to market close.
    assert (result['published_at'] == cutoff.tz_convert('UTC')).all()
    assert result['publication_basis'].eq('captured_dataset').all()


def test_nikkei_csv_parses_publisher_format_and_skips_copyright_footer():
    text = 'データ日付,終値,始値,高値,安値\n2026/10/02,100,98,101,97\n2026/10/05,102,100,103,99\n本資料は日経の著作物\n'
    frame = overseas.parse_daily_csv(text, 'nikkei225', pd.Timestamp('2026-10-06T07:00:00+08:00'))
    assert frame['value'].tolist() == [100, 102]
    assert frame.iloc[-1]['completed_at'] == pd.Timestamp('2026-10-05T15:30:00+09:00')


@pytest.mark.parametrize('text', ['captcha', 'observation_date,SP500\n2026-10-02,-1\n',
                                   'observation_date,OTHER\n2026-10-02,100\n'])
def test_invalid_source_never_becomes_zero_or_index_value(text):
    with pytest.raises(ValueError):
        overseas.parse_daily_csv(text, 'sp500', pd.Timestamp('2026-10-06T07:00:00+08:00'))


def test_overseas_summary_shows_all_indices_and_missing_history():
    frame = overseas.parse_daily_csv('observation_date,SP500\n2026-10-01,100\n2026-10-02,102\n',
                                    'sp500', pd.Timestamp('2026-10-06T07:00:00+08:00'))
    summary = overseas.overseas_summary(frame, pd.Timestamp('2026-10-06T07:00:00+08:00'))
    assert len(summary) == 4
    row = summary[summary['指标'].eq('标普500')].iloc[0]
    assert row['当日涨跌幅'] == '+2.00%'
    assert row['5日涨跌幅'] == '缺数据'
    assert row['交易日期'] == '2026-10-02'
    assert summary[summary['指标'].eq('KOSPI')].iloc[0]['收盘点位'] == '缺数据'

