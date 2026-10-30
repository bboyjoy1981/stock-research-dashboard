import pandas as pd
import pytest
import requests

from src.temperature_sources import collect_temperature_sources, parse_nbs_release


PMI_URL = 'https://www.stats.gov.cn/zwfwck/sjfb/202609/t20260930_1965449.html'
PMI_HTML = '''<html><title>2026年9月中国采购经理指数运行情况</title>
<p>发布时间：2026-09-30 09:30</p><p>9月份，制造业采购经理指数（PMI）为50.1%，比上月上升0.3个百分点。</p></html>'''


def test_nbs_release_parses_period_value_and_real_publication():
    result = parse_nbs_release(PMI_HTML, PMI_URL, 'cn_pmi',
        pd.Timestamp('2026-10-06T12:00:00+08:00'), pd.Timestamp('2026-10-31T09:30:00+08:00'))
    assert result.iloc[0]['value'] == 50.1
    assert result.iloc[0]['data_period'] == '2026-09'
    assert result.iloc[0]['published_at'] == pd.Timestamp('2026-09-30T09:30:00+08:00')


def test_cpi_yoy_is_not_monthly_change():
    html = '''<title>2026年8月份居民消费价格同比上涨0.8%</title>
    发布时间：2026-09-09 09:30
    2026年8月份，全国居民消费价格同比上涨0.8%。8月份，全国居民消费价格环比上涨0.4%。'''
    result = parse_nbs_release(html, 'https://www.stats.gov.cn/example', 'cn_cpi_yoy',
        pd.Timestamp('2026-10-06T12:00:00+08:00'), pd.Timestamp('2026-10-14T09:30:00+08:00'))
    assert result.iloc[0]['value'] == .8
    assert result.iloc[0]['data_period'] == '2026-08'


@pytest.mark.parametrize('html', ['<title>验证</title>请输入验证码',
    PMI_HTML.replace('发布时间：2026-09-30 09:30', ''),
    PMI_HTML.replace('50.1%', '50.1'), '<html></html>'])
def test_missing_publication_or_schema_or_verification_page_rejected(html):
    with pytest.raises(ValueError):
        parse_nbs_release(html, PMI_URL, 'cn_pmi',
            pd.Timestamp('2026-10-06T12:00:00+08:00'), pd.Timestamp('2026-10-31T09:30:00+08:00'))


def test_collector_network_failure_returns_missing_not_zero(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout('timed out')
    monkeypatch.setattr('src.temperature_sources.get_public', timeout)
    result = collect_temperature_sources(pd.Timestamp('2026-09-30T15:00:00+08:00'))
    assert result['observations'].empty
    assert len(result['errors']) == 1
    assert result['source_status'][1]['状态'] == '截止后发布'
    assert result['source_status']


def test_future_release_not_collected_for_earlier_replay(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('future release should not be requested')
    monkeypatch.setattr('src.temperature_sources.get_public', unexpected)
    result = collect_temperature_sources(pd.Timestamp('2026-08-01T15:00:00+08:00'))
    assert result['observations'].empty


def test_successful_collect_and_cutoff_filter(monkeypatch):
    class Response:
        status_code = 200
        content = PMI_HTML.encode('utf-8')
        def raise_for_status(self):
            pass
    monkeypatch.setattr('src.temperature_sources.get_public', lambda *a, **k: Response())
    result = collect_temperature_sources(pd.Timestamp('2026-09-30T15:00:00+08:00'))
    assert result['observations']['indicator_id'].tolist() == ['cn_pmi']
    assert not result['errors']
    assert result['source_status'][1]['状态'] == '截止后发布'


def test_wrong_document_never_substitutes_for_due_cpi(monkeypatch):
    class Response:
        content = PMI_HTML.encode('utf-8')

        def raise_for_status(self):
            pass

    monkeypatch.setattr('src.temperature_sources.get_public', lambda *a, **k: Response())
    result = collect_temperature_sources(pd.Timestamp('2026-10-15T15:00:00+08:00'))
    assert result['observations']['indicator_id'].tolist() == ['cn_pmi']
    assert len(result['errors']) == 1
    assert result['source_status'][1]['状态'] == '采集失败'
