import pandas as pd
import pytest

from src.temperature_store import load_observations, save_observations
from test_temperature_data import row


def test_empty_store_returns_empty_frame(tmp_path):
    assert load_observations(tmp_path).empty


def test_store_roundtrip_is_idempotent_and_preserves_vintages(tmp_path):
    original = pd.DataFrame([row()])
    save_observations(original, tmp_path)
    save_observations(original, tmp_path)
    save_observations(pd.DataFrame([row(value=49.8, revision=True, version='r1',
                                      published_at='2026-10-02T09:30:00+08:00')]), tmp_path)
    assert sorted(load_observations(tmp_path)['value']) == [49.8, 50.1]


def test_invalid_update_preserves_existing_store(tmp_path):
    save_observations(pd.DataFrame([row()]), tmp_path)
    with pytest.raises(ValueError):
        save_observations(pd.DataFrame([row(value=42)]), tmp_path)
    assert load_observations(tmp_path)['value'].tolist() == [50.1]


def test_atomic_replace_failure_preserves_previous_store(tmp_path, monkeypatch):
    save_observations(pd.DataFrame([row()]), tmp_path)
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr('src.temperature_store.os.replace', fail)
    with pytest.raises(OSError):
        save_observations(pd.DataFrame([row(data_period='2026-08')]), tmp_path)
    assert load_observations(tmp_path)['data_period'].tolist() == ['2026-09']
def test_mixed_source_optional_provenance_roundtrips_as_null(tmp_path):
    from test_temperature_data import row
    first = row()
    first['schedule_url'] = 'https://www.stats.gov.cn/schedule'
    second = row()
    second.update(indicator_id='sp500', unit='points', publication_basis='captured_dataset')
    save_observations(pd.DataFrame([first, second]), tmp_path)
    stored = load_observations(tmp_path)
    assert len(stored) == 2
    assert stored.loc[stored['indicator_id'].eq('sp500'), 'publication_basis'].iloc[0] == 'captured_dataset'

