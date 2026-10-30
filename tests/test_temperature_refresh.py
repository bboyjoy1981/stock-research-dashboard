import pandas as pd
import pytest

from test_temperature_data import row
from src.temperature_store import load_observations, save_observations


@pytest.fixture(autouse=True)
def offline_ism_collector(monkeypatch):
    # Each test controls other collectors; ISM must not reach the real network.
    monkeypatch.setattr('src.temperature_refresh.collect_ism_history', lambda captured_at:
        dict(observations=pd.DataFrame(), source_status=[], errors=[],
             fetched_at=captured_at.isoformat()))


def test_refresh_preserves_success_when_other_collector_fails(tmp_path, monkeypatch):
    from src import temperature_refresh as refresh

    original = pd.DataFrame([row(value=50)])
    save_observations(original, tmp_path)
    incoming = row(indicator_id='sp500', value=100, unit='points', market_coverage='SP500')
    monkeypatch.setattr(refresh, 'collect_overseas_sources', lambda captured_at:
        dict(observations=pd.DataFrame([incoming]), source_status=[dict(来源='标普500', 状态='成功')],
             errors=[], fetched_at=captured_at.isoformat()))

    def failed(captured_at):
        raise ValueError('来源字段变更')

    monkeypatch.setattr(refresh, 'collect_history_sources', failed)
    result = refresh.refresh_latest_sources(tmp_path, pd.Timestamp('2026-10-06T12:00:00Z'))
    stored = load_observations(tmp_path)
    assert set(stored.indicator_id) == {'cn_pmi', 'sp500'}
    assert result['saved_count'] == 1
    assert any('来源字段变更' in error for error in result['errors'])


def test_refresh_reports_individual_history_failures(tmp_path, monkeypatch):
    from src import temperature_refresh as refresh

    monkeypatch.setattr(refresh, 'collect_history_sources', lambda captured_at:
        dict(observations=pd.DataFrame(), source_status=[dict(指标='gold', 来源='https://example.com',
             状态='失败', 说明='超时')], fetched_at=captured_at.isoformat()))
    monkeypatch.setattr(refresh, 'collect_overseas_sources', lambda captured_at:
        dict(observations=pd.DataFrame(), source_status=[], errors=[], fetched_at=captured_at.isoformat()))
    result = refresh.refresh_latest_sources(tmp_path, pd.Timestamp('2026-10-06T12:00:00Z'))
    assert result['saved_count'] == 0
    assert any('超时' in error for error in result['errors'])
    assert not (tmp_path / 'observations.json').exists()


def test_refresh_rejects_naive_capture_before_any_fetch(tmp_path):
    from src.temperature_refresh import refresh_latest_sources

    with pytest.raises(ValueError, match='时区'):
        refresh_latest_sources(tmp_path, pd.Timestamp('2026-10-06'))
