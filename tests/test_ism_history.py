import pandas as pd
import pytest


def fixture(value='47.2', period='Sep 2024'):
    return f'''<h1>September 2024 Manufacturing ISM Report</h1>
    <p>News provided by Institute for Supply Management</p>
    <table><tr><td>Month</td><td>Manufacturing PMI®</td><td>Month</td><td>Manufacturing PMI®</td></tr>
    <tr><td>{period}</td><td>{value}</td><td>Aug 2024</td><td>47.2</td></tr>
    <tr><td>Average for 12 months</td><td>48.0</td><td>Low</td><td>46.6</td></tr></table>'''


def test_history_table_parses_only_monthly_headline_pmi_and_preserves_capture_time():
    from src.ism_history import parse_ism_history
    f = parse_ism_history(fixture(), 'https://www.prnewswire.com/test', '2024-09',
                          '2026-10-07T05:00:00Z')
    assert f['data_period'].tolist() == ['2024-08', '2024-09']
    assert f['value'].tolist() == [47.2, 47.2]
    assert f['published_at'].eq(pd.Timestamp('2026-10-07T05:00:00Z')).all()
    assert f['publication_basis'].eq('captured_dataset').all()


@pytest.mark.parametrize('html,end', [
    (fixture('101'), '2024-09'),
    (fixture(period='Sep 2027'), '2024-09'),
    (fixture().replace('Manufacturing PMI®', 'Services PMI®'), '2024-09'),
    (fixture().replace('Institute for Supply Management', 'Other issuer'), '2024-09'),
    (fixture().replace('Aug 2024', 'Sep 2024').replace('<td>47.2</td></tr>', '<td>48.0</td></tr>'), '2024-09'),
])
def test_ambiguous_invalid_or_wrong_indicator_reports_are_rejected(html,end):
    from src.ism_history import parse_ism_history
    with pytest.raises(ValueError):
        parse_ism_history(html, 'https://www.prnewswire.com/test', end, '2026-10-07T05:00:00Z')
