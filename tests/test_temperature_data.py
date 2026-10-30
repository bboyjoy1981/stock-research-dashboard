import pandas as pd
import pytest

from src.temperature_data import observations_at, validate_observations


def row(**changes):
    result = dict(indicator_id='cn_pmi', value=50.1, unit='index',
                  market_coverage='CN manufacturing NBS', data_period='2026-09',
                  published_at='2026-09-30T09:30:00+08:00',
                  fetched_at='2026-10-06T12:00:00+08:00',
                  completed_at='2026-09-30T09:30:00+08:00',
                  valid_until='2026-10-31T09:30:00+08:00',
                  source_url='https://www.stats.gov.cn/example',
                  version='original', revision=False)
    result.update(changes)
    return result


def test_future_revision_does_not_replace_original_vintage():
    frame = pd.DataFrame([row(), row(value=49.8, version='revision-1', revision=True,
                                    published_at='2026-10-02T09:30:00+08:00')])
    selected = observations_at(frame, pd.Timestamp('2026-09-30T15:00:00+08:00'))
    assert selected['value'].tolist() == [50.1]


@pytest.mark.parametrize('field,value', [
    ('published_at', '2026-09-30 09:30'), ('source_url', ''),
    ('value', float('nan')), ('value', float('inf')), ('unit', ''),
])
def test_invalid_contract_rejected(field, value):
    with pytest.raises(ValueError):
        validate_observations(pd.DataFrame([row(**{field: value})]))


def test_duplicate_fetch_is_idempotent():
    frame = pd.DataFrame([row(), row(fetched_at='2026-10-07T12:00:00+08:00')])
    assert len(validate_observations(frame)) == 1


@pytest.mark.parametrize('changes', [dict(unit='percent'), dict(market_coverage='other')])
def test_mixing_measurement_definitions_is_rejected(changes):
    with pytest.raises(ValueError):
        validate_observations(pd.DataFrame([row(), row(data_period='2026-08', **changes)]))


def test_expired_observation_is_unavailable_at_boundary():
    assert observations_at(pd.DataFrame([row()]),
                           pd.Timestamp('2026-10-31T09:30:00+08:00')).empty


def test_unfinished_foreign_session_is_unavailable():
    frame = pd.DataFrame([row(completed_at='2026-09-30T16:00:00+08:00')])
    assert observations_at(frame, pd.Timestamp('2026-09-30T15:00:00+08:00')).empty


def test_conflicting_values_for_same_vintage_are_rejected():
    with pytest.raises(ValueError):
        validate_observations(pd.DataFrame([row(), row(value=49)]))


def test_naive_cutoff_is_rejected():
    with pytest.raises(ValueError):
        observations_at(pd.DataFrame([row()]), pd.Timestamp('2026-09-30'))


def test_empty_observations_are_valid():
    assert observations_at(pd.DataFrame(), pd.Timestamp('2026-09-30T15:00:00+08:00')).empty


def test_same_time_conflicting_sources_cannot_be_selected_arbitrarily():
    frame = pd.DataFrame([row(), row(value=49, source_url='https://example.org/release')])
    with pytest.raises(ValueError):
        observations_at(frame, pd.Timestamp('2026-09-30T15:00:00+08:00'))


def test_reverified_equal_release_is_not_hidden_by_expired_dataset_capture():
    original = row(fetched_at='2026-10-08T10:00:00+08:00')
    capture = row(published_at='2026-10-06T12:00:00+08:00',
                  fetched_at='2026-10-06T12:00:00+08:00',
                  valid_until='2026-10-07T12:00:00+08:00',
                  version='capture', publication_basis='captured_dataset')
    selected = observations_at(pd.DataFrame([original, capture]),
                               pd.Timestamp('2026-10-08T11:00:00+08:00'))
    assert selected['version'].tolist() == ['original']


@pytest.mark.parametrize('changes', [dict(value=49.8), dict(revision=True),
                                   dict(source_url='https://example.org/other')])
def test_expired_changed_capture_cannot_fall_back_to_original(changes):
    capture = row(published_at='2026-10-06T12:00:00+08:00',
                  valid_until='2026-10-07T12:00:00+08:00',
                  version='capture', publication_basis='captured_dataset', **changes)
    original = row(fetched_at='2026-10-08T10:00:00+08:00')
    assert observations_at(pd.DataFrame([original, capture]),
                           pd.Timestamp('2026-10-08T11:00:00+08:00')).empty


def test_future_reverification_does_not_rescue_expired_capture():
    original = row(fetched_at='2026-10-09T10:00:00+08:00')
    capture = row(published_at='2026-10-06T12:00:00+08:00',
                  valid_until='2026-10-07T12:00:00+08:00',
                  version='capture', publication_basis='captured_dataset')
    assert observations_at(pd.DataFrame([original, capture]),
                           pd.Timestamp('2026-10-08T11:00:00+08:00')).empty
