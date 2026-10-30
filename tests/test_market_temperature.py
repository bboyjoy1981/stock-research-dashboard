from pathlib import Path
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from test_temperature_data import row


@pytest.fixture(autouse=True)
def offline_latest_refresh(monkeypatch):
    # Network collectors are external; keep AppTests deterministic and offline.
    monkeypatch.setattr('src.market_temperature.refresh_latest_sources', lambda directory, *, include_ashare=False:
        dict(saved_count=0, source_status=[], errors=[], fetched_at='2026-10-07T05:00:00Z'),
        raising=False)


def test_update_refreshes_latest_research_without_backdating_replay(tmp_path, monkeypatch):
    from src.temperature_store import save_observations, load_observations

    monkeypatch.setattr('src.market_temperature.collect_temperature_sources', lambda cutoff:
        dict(observations=pd.DataFrame(), errors=[], source_status=[], fetched_at='2026-10-07T05:00:00Z'))

    def refresh(directory, *, include_ashare=False):
        assert include_ashare is True
        record = row(indicator_id='sp500', value=100, unit='points', market_coverage='SP500',
                     published_at='2026-10-07T05:00:00Z', fetched_at='2026-10-07T05:00:00Z',
                     valid_until='2026-10-08T05:00:00Z')
        save_observations(pd.DataFrame([record]), directory)
        return dict(saved_count=1, source_status=[dict(来源='标普500', 状态='成功')],
                    errors=[], fetched_at='2026-10-07T05:00:00Z')

    monkeypatch.setattr('src.market_temperature.refresh_latest_sources', refresh)
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_latest_directory=tmp_path / 'latest'))
    app.button(key='update_market_temperature').click().run(timeout=30)
    assert not app.exception
    assert len(load_observations(tmp_path / 'latest')) == 1
    assert load_observations(tmp_path).empty
    assert any('最新研究' in item.value for item in app.caption)


def review_script():
    from src.market_temperature import _render_commodity_quotes, _render_environment_facts
    _render_commodity_quotes()
    _render_environment_facts()


def test_malformed_review_snapshots_do_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr('src.market_temperature.DEFAULT_DIRECTORY', tmp_path)
    for payload in ({}, {'checked_at': 'bad', 'quotes': []},
                    {'checked_at': '2026-10-06T02:40:00Z', 'quotes': [{'price': 1, 'previous_price': 0}]}):
        for name in ('commodity_review.json', 'environment_review.json'):
            (tmp_path / name).write_text(json.dumps(payload), encoding='utf-8')
        app = AppTest.from_function(review_script).run()
        assert not app.exception
        assert not app.metric


def test_stale_commodity_review_requires_reverification(tmp_path, monkeypatch):
    from src.market_temperature import DEFAULT_DIRECTORY
    payload = json.loads((DEFAULT_DIRECTORY / 'commodity_review.json').read_text(encoding='utf-8'))
    payload['checked_at'] = '2020-01-01T00:00:00Z'
    for item in payload['quotes']:
        item.update(date='2019-12-31', previous_date='2019-12-30')
    (tmp_path / 'commodity_review.json').write_text(json.dumps(payload), encoding='utf-8')
    monkeypatch.setattr('src.market_temperature.DEFAULT_DIRECTORY', tmp_path)
    app = AppTest.from_function(review_script).run()
    assert not app.exception
    assert any('需重新核实' in item.value for item in app.caption)


def script():
    import streamlit as st
    from src.market_temperature import render_market_temperature
    render_market_temperature(st.session_state['data'])


def app_for(data, details=True, group='宏观环境'):
    app = AppTest.from_function(script)
    app.session_state['data'] = data
    app.run(timeout=30)
    if details:
        app.button(key='open_market_temperature').click().run(timeout=30)
        if group != '宏观环境':
            app.segmented_control(key='temperature_group').set_value(group).run(timeout=30)
    return app


def test_comparison_reference_is_displayed_without_entering_temperature_score(tmp_path):
    from src.temperature_store import save_observations
    scope = '沪深两市两融'
    current = row(indicator_id='a_margin_balance', unit='CNY', market_coverage=scope,
                  data_period='2026-09-29', value=200, valid_until='2026-10-09T00:00:00Z')
    history = [row(indicator_id='a_margin_balance', unit='CNY', market_coverage=scope,
                   data_period=str(d.date()), value=100) for d in pd.bdate_range('2015-01-01', periods=120)]
    save_observations(pd.DataFrame([current]), tmp_path / 'latest')
    save_observations(pd.DataFrame(history), tmp_path / 'comparison')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_latest_cutoff='2026-10-07T00:00:00Z'), group='A股热度')
    assert not app.exception
    assert any('2015年：:red[**高于参考期常态**]' in x.value for x in app.markdown)
    assert any('100.0%' in x.value for x in app.markdown)
    assert any('可评分权重 0/65' in x.value for x in app.caption)


def test_accounts_show_separate_2015_spring_and_summer_benchmarks(tmp_path):
    from src.temperature_store import save_observations
    save_observations(pd.DataFrame([row(indicator_id='a_new_accounts', value=2397300,
        unit='accounts', market_coverage='沪市A股账户', data_period='2026-08')]), tmp_path / 'latest')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
        temperature_latest_cutoff='2026-10-07T00:00:00Z'), group='A股热度')
    assert not app.exception
    assert any('2015年7—9月' in x.value and '247.44万户' in x.value for x in app.markdown)
    assert any('2015年4—6月' in x.value and '701.83万户' in x.value for x in app.markdown)


def test_shenzhen_index_is_included_in_historical_comparison(tmp_path):
    from src.temperature_store import save_observations
    save_observations(pd.DataFrame([row(indicator_id='szse', value=12887.62,
        unit='points', market_coverage='深证成指', data_period='2026-09-30')]), tmp_path / 'latest')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
        temperature_latest_cutoff='2026-10-07T00:00:00Z'), group='A股热度')
    assert not app.exception
    assert any(x.value == '#### 深证成指' for x in app.markdown)


def test_missing_data_renders_text_grade_and_three_traceable_groups(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       stocks=pd.DataFrame()))
    assert not app.exception
    assert next(item for item in app.metric if item.label == '市场温度').value == '暂无法判断'
    options = app.segmented_control(key='temperature_group').options
    assert len(options) == 3
    assert all(name in option for name, option in zip(('宏观环境', '海外股市', 'A股热度'), options))
    assert any('未完成历史验证' in item.value for item in app.caption)


def test_latest_ashare_reference_is_separate_from_replay(tmp_path):
    from src.temperature_store import save_observations
    record = row()
    record.update(indicator_id='a_amount', value=1e12, unit='CNY',
                  data_period='2026-09-30', published_at='2026-10-06T00:00:00Z',
                  fetched_at='2026-10-06T00:00:00Z', valid_until='2026-10-08T00:00:00Z')
    save_observations(pd.DataFrame([record]), tmp_path / 'latest')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_latest_cutoff='2026-10-07T00:00:00Z'), group='A股热度')
    assert not app.exception
    assert any('最新A股核算参考' in item.value for item in app.markdown)
    assert any('不覆盖所选历史复盘' in item.value for item in app.caption)
    assert any('A股成交额' in table.value.to_string() for table in app.dataframe)


def test_group_navigation_is_emphasized_without_duplicate_blue_banner(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    assert not any('三大板块' in item.value for item in app.info)
    assert app.segmented_control(key='temperature_group').value == '宏观环境'
    app.segmented_control(key='temperature_group').set_value('海外股市').run(timeout=30)
    assert not app.exception
    assert not any('利率决议与外围风险' in item.value for item in app.markdown)


def test_each_group_leads_with_conclusion_and_trend_belongs_to_ashare(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    assert not app.exception
    assert not any('动态年线' in item.label for item in app.expander)
    app.segmented_control(key='temperature_group').set_value('A股热度').run(timeout=30)
    assert not app.exception
    assert any('动态年线' in item.label for item in app.expander)
    assert any('分项判断' in item.value for item in app.markdown)


def test_overseas_and_ashare_explain_time_basis_without_expansion(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    for name in ('海外股市', 'A股热度'):
        app.segmented_control(key='temperature_group').set_value(name).run(timeout=30)
        text = '\n'.join(item.value for item in list(app.markdown) + list(app.caption))
        assert '测算口径' in text
        assert '2026-09-30' in text
        assert '历史比较区间' in text
        assert '# 分项判断：:orange[**暂无法判断**]' in text
    app.segmented_control(key='temperature_group').set_value('海外股市').run(timeout=30)
    assert '5日 / 20日' in '\n'.join(x.value for x in app.caption)


def test_available_fact_has_source_period_and_publication_visible(tmp_path):
    observations = pd.DataFrame([row()])
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_observations=observations))
    assert not app.exception
    tables = [item.value for item in app.dataframe]
    facts = next(table for table in tables if '发布时间' in table)
    assert facts.iloc[0]['数据期'] == '2026-09'
    assert facts.iloc[0]['来源'] == 'https://www.stats.gov.cn/example'
    assert '2026-09-30' in facts.iloc[0]['发布时间']
    assert not any('internal_score' in table.columns for table in tables)


def test_update_failure_keeps_existing_data_and_page_usable(tmp_path, monkeypatch):
    def failed(*args):
        raise OSError('source offline')
    monkeypatch.setattr('src.market_temperature.collect_temperature_sources', failed)
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_observations=pd.DataFrame([row()])))
    app.button(key='update_market_temperature').click().run(timeout=30)
    assert not app.exception
    assert app.warning
    assert any('source offline' in warning.value for warning in app.warning)
    assert any('发布时间' in item.value.columns for item in app.dataframe)


def test_unverified_geo_risk_never_claims_safe(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    assert not app.exception
    assert any('不按“存在战争”自动加减分' in item.value for item in app.caption)


def test_invalid_stored_data_does_not_crash_update(tmp_path, monkeypatch):
    (tmp_path / 'observations.json').write_text('not-json', encoding='utf-8')
    monkeypatch.setattr('src.market_temperature.collect_temperature_sources', lambda cutoff:
        dict(observations=pd.DataFrame([row()]), errors=[], source_status=[],
             fetched_at='2026-10-06T12:00:00+08:00'))
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    app.button(key='update_market_temperature').click().run(timeout=30)
    assert not app.exception
    assert app.warning


def test_overview_integrates_new_temperature_and_preserves_state():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=30)
    assert not app.exception
    assert any(item.label == '市场温度' for item in app.metric)
    assert any(item.label == '市场状态' for item in app.metric)


def test_successful_update_persists_fact_and_is_not_repeated_on_rerun(tmp_path, monkeypatch):
    from src.temperature_store import load_observations
    attempts = []
    def collect(cutoff):
        attempts.append(cutoff)
        return dict(observations=pd.DataFrame([row()]), errors=[], source_status=[],
                    fetched_at='2026-10-06T12:00:00+08:00')
    monkeypatch.setattr('src.market_temperature.collect_temperature_sources', collect)
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    app.button(key='update_market_temperature').click().run(timeout=30)
    assert not app.exception
    assert load_observations(tmp_path)['value'].tolist() == [50.1]
    app.run(timeout=30)
    assert len(attempts) == 1


def test_complete_raw_fixture_displays_descriptive_grade_not_numeric_score(tmp_path):
    # Raw, explicitly test-only histories exercise the real scorer and renderer.
    from test_temperature_rules import monthly_series, daily_series
    records = []
    for key in ('cn_pmi', 'us_pmi'):
        records += monthly_series(key, [50] * 57)
    for key in ('cn_cpi_yoy', 'us_cpi_yoy', 'us_core_cpi_yoy',
                'cn_policy_rate', 'us_policy_rate', 'eu_policy_rate', 'jp_policy_rate'):
        records += monthly_series(key, [2] * 57, unit='percent')
    records += monthly_series('a_new_accounts', [1000] * 57, unit='accounts')
    for key in ('sp500', 'nasdaq', 'nikkei225', 'kospi', 'sse', 'szse', 'chinext', 'star50', 'csi300'):
        records += daily_series(key, [100] * 200)
    for key in ('gold', 'oil'):
        records += daily_series(key, [100] * 200, unit='USD')
    for key in ('a_breadth', 'a_newhigh_low_60', 'a_limit_balance', 'a_margin_buy_ratio'):
        records += daily_series(key, [.5] * 200, unit='ratio')
    for key in ('a_amount', 'a_margin_balance'):
        records += daily_series(key, [1000] * 200, unit='CNY')
    # Move daily fixture to end on selected day; this is a test calendar only.
    dates = pd.bdate_range(end='2026-09-30', periods=200)
    daily = [record for record in records if len(record['data_period']) == 10]
    by_key = {}
    for record in daily:
        by_key.setdefault(record['indicator_id'], []).append(record)
    for rows in by_key.values():
        for record, day in zip(rows, dates):
            pub = day.tz_localize('Asia/Shanghai') + pd.Timedelta(hours=15)
            record.update(data_period=day.strftime('%Y-%m-%d'), published_at=pub,
                          completed_at=pub, fetched_at=pub+pd.Timedelta(hours=1),
                          valid_until=pub+pd.Timedelta(days=7), market_coverage='沪深固定复权样本')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_observations=pd.DataFrame(records)))
    assert not app.exception
    assert next(item for item in app.metric if item.label == '市场温度').value == '中性'
    assert not any('/100' in item.value for item in app.metric)
    assert not any('internal_score' in item.value.columns for item in app.dataframe)
def test_homepage_has_only_grade_summary_and_details_entry(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path), details=False)
    assert not app.exception
    headline = app.get_by_key('pulse_market_temperature_headline')
    assert headline.metric[0].label == '市场温度'
    assert len(app.get('vega_lite_chart')) == 1
    assert not app.dataframe
    assert not app.tabs
    assert app.button(key='open_market_temperature').label == '查看详情'
    assert not any(item.key == 'update_market_temperature' for item in app.button)
    assert not any('最近一次利率决议' in item.value for item in app.markdown)
    assert not headline.expander


def test_weight_chart_encodes_model_weights_not_data_coverage():
    from src.market_temperature import temperature_weight_chart
    chart = temperature_weight_chart().to_dict()
    dataset = next(iter(chart['datasets'].values()))
    assert {row['类别']: row['权重'] for row in dataset} == {'宏观环境': 15, '海外股市': 20, 'A股热度': 65}
    assert chart['layer'][0]['mark']['type'] == 'bar'
    assert chart['layer'][0]['encoding']['x']['stack'] == 'zero'


def test_environment_facts_remain_available_in_details(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    assert not app.exception
    facts = app.get_by_key('temperature_environment_facts')
    assert facts.expander
    text = '\n'.join(item.value for item in facts.markdown)
    assert '美联储' in text and '3.75%–4.00%' in text
    assert '俄乌' in text and '伊朗' in text
    assert 'https://' in text
    assert any('不计入' in item.value for item in facts.caption)


def test_closing_details_removes_all_detail_content(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    app.button(key='close_market_temperature').click().run(timeout=30)
    assert not app.exception
    assert not app.tabs
    assert not app.dataframe
    assert len(app.get('vega_lite_chart')) == 1


def test_homepage_exposes_weights_and_temperature_standard(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path), details=False)
    text = '\n'.join(item.value for item in app.caption)
    assert '宏观环境 15%' in text and 'A股热度 65%' in text
    assert '过冷' in text and '过热' in text


def test_homepage_separates_trend_stage_from_temperature(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path), details=False)
    assert any('趋势阶段' in item.value for item in app.caption)


def test_latest_index_history_provides_separate_stage_without_backdating(tmp_path):
    from test_temperature_stage import fixture
    from src.temperature_store import save_observations
    frame, _ = fixture(list(range(3800,4100)))
    frame['published_at'] = pd.Timestamp('2026-10-06T00:00:00Z')
    frame['fetched_at'] = pd.Timestamp('2026-10-06T00:00:00Z')
    save_observations(frame, tmp_path / 'latest')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_latest_cutoff=pd.Timestamp('2026-10-06T06:00:00Z')), details=True, group='A股热度')
    assert next(item for item in app.metric if item.label == '市场温度').value == '暂无法判断'
    assert any('趋势阶段：上升趋势' in item.value for item in app.caption)
    assert any('事后参考' in item.value for item in app.caption)
    assert any('本轮最高收盘' in item.value for item in app.dataframe)


def test_commodity_quotes_show_separate_prices_and_comparison_dates(tmp_path, monkeypatch):
    import json

    snapshot = {
        'checked_at': '2026-10-06T10:40:00+08:00',
        'quotes': [
            dict(id='gold', name='黄金', benchmark='测试现货日收盘基准',
                 unit='美元/金衡盎司', price=4140.52, date='2026-10-02',
                 previous_price=4177.39, previous_date='2026-10-01',
                 source_name='测试来源', source_url='https://example.com/gold',
                 availability='测试历史快照'),
            dict(id='oil', name='原油', benchmark='测试布伦特现货基准',
                 unit='美元/桶', price=113.96, date='2026-09-29',
                 previous_price=119.97, previous_date='2026-09-28',
                 source_name='测试来源', source_url='https://example.com/oil',
                 availability='测试历史快照'),
        ],
    }
    (tmp_path / 'commodity_review.json').write_text(json.dumps(snapshot), encoding='utf-8')
    monkeypatch.setattr('src.market_temperature.DEFAULT_DIRECTORY', tmp_path)
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    gold = app.get_by_key('temperature_quote_gold')
    oil = app.get_by_key('temperature_quote_oil')
    assert gold.metric[0].value == '4,140.52'
    assert '-0.88%' in gold.metric[0].delta
    assert oil.metric[0].value == '113.96'
    assert '-5.01%' in oil.metric[0].delta
    assert any('2026-10-01' in item.value and '4,177.39' in item.value for item in gold.caption)
    assert any('2026-09-28' in item.value and '119.97' in item.value for item in oil.caption)
    assert any('不计入' in item.value for item in app.caption)


def test_policy_conclusions_are_badges_and_long_explanations_collapsed(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    facts = app.get_by_key('temperature_environment_facts')
    text = '\n'.join(item.value for item in facts.markdown)
    assert ':red-badge[加息25基点]' in text
    assert ':orange-badge[变动幅度待核实]' in text
    assert ':orange-badge[持续风险 · 未独立确认]' in text
    assert all(not item.proto.expanded for item in facts.expander)


def test_raw_indicator_catalog_keeps_missing_inputs_visible(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_observations=pd.DataFrame([row()])))
    assert not app.exception
    catalog = next(item.value for item in app.dataframe if '接入状态' in item.value.columns)
    assert set(catalog['类别']) == {'宏观环境'}
    assert catalog.loc[catalog['指标'].eq('中国制造业PMI'), '原始值'].iloc[0] == 50.1
    assert catalog.loc[catalog['指标'].eq('美国制造业PMI'), '接入状态'].iloc[0] == '缺数据'


def test_derived_values_and_history_shortfalls_are_exposed(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_observations=pd.DataFrame([row()])))
    assert not app.exception
    audit = next(item.value for item in app.dataframe if '最低历史样本数' in item.value.columns)
    level = audit.loc[audit['计算项'].eq('原始水平')].iloc[0]
    assert level['当前衍生值'] == 50.1
    assert level['有效历史样本数'] == 0
    assert level['最低历史样本数'] == 36


def test_latest_overseas_is_visible_but_never_changes_historical_headline(tmp_path):
    from src.overseas_temperature import parse_daily_csv
    from src.temperature_store import save_observations
    captured = pd.Timestamp('2026-10-06T07:00:00+08:00')
    frame = parse_daily_csv('observation_date,SP500\n2026-10-01,100\n2026-10-02,102\n', 'sp500', captured)
    save_observations(frame, tmp_path / 'latest')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
                       temperature_latest_cutoff=captured), group='海外股市')
    assert not app.exception
    assert next(item for item in app.metric if item.label == '市场温度').value == '暂无法判断'
    table = next(item.value for item in app.dataframe if '收盘点位' in item.value)
    assert table.iloc[0]['收盘点位'] == '102.00'
    assert table.iloc[0]['当日涨跌幅'] == '+2.00%'
    assert table.iloc[0]['交易日期'] == '2026-10-02'
    assert table.iloc[-1]['收盘点位'] == '缺数据'
    assert any('不覆盖' in item.value and '历史复盘' in item.value for item in app.caption)


def test_corrupt_latest_overseas_does_not_break_historical_details(tmp_path):
    (tmp_path / 'latest').mkdir()
    (tmp_path / 'latest' / 'observations.json').write_text('not-json', encoding='utf-8')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path), group='海外股市')
    assert not app.exception
    assert any('最新海外数据读取失败' in item.value for item in app.caption)


def test_macro_summary_omits_duplicate_commodity_row(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path))
    summary = next(item.value for item in app.dataframe if '依据或缺口' in item.value and '指标' in item.value)
    assert '黄金与原油' not in summary['指标'].tolist()
    catalog = next(item.value for item in app.dataframe if '接入状态' in item.value)
    assert any('黄金' in name for name in catalog['指标'])


def test_ashare_details_do_not_mix_macro_sources_or_inputs(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
        temperature_observations=pd.DataFrame([row()])), group='A股热度')
    assert not app.exception
    # The overall reference above this container intentionally covers all groups.
    details = app.get_by_key('pulse_market_temperature')
    tables = '\n'.join(item.value.to_string() for item in details.dataframe)
    assert 'PMI' not in tables and 'CPI' not in tables
    catalog = next(item.value for item in details.dataframe if '接入状态' in item.value)
    assert set(catalog['类别']) == {'A股热度'}
    assert any('历史复盘' in item.label and not item.proto.expanded for item in app.expander)


def test_ashare_comparison_details_are_collapsed(tmp_path):
    from src.temperature_store import save_observations
    save_observations(pd.DataFrame([row(indicator_id='a_new_accounts', value=2397300,
        unit='accounts', market_coverage='沪市A股账户', data_period='2026-08')]), tmp_path / 'latest')
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path,
        temperature_latest_cutoff='2026-10-07T00:00:00Z'), group='A股热度')
    assert not app.exception
    summary = next(item.value for item in app.dataframe if '对比时期' in item.value)
    assert '2015年' in summary['对比时期'].tolist()
    assert '239.73万户' in summary['当前值'].tolist()
    assert any('沪市A股月度' in item.label and not item.proto.expanded for item in app.expander)


def test_ashare_collection_status_preserves_actual_failures(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path), group='A股热度')
    app.session_state['temperature_source_status'] = [
        dict(指标='a_margin_balance', 来源='沪市两融', 状态='失败', 说明='测试：来源超时'),
        dict(指标='cn_pmi', 来源='中国制造业PMI', 状态='成功')]
    app.run(timeout=30)
    statuses = next(item.value for item in app.dataframe if '状态' in item.value and '说明' in item.value)
    assert statuses['状态'].tolist() == ['失败']
    assert statuses['说明'].tolist() == ['测试：来源超时']


def test_ashare_audit_has_no_duplicate_entry(tmp_path):
    app = app_for(dict(import_date='2026-09-30', temperature_directory=tmp_path), group='A股热度')
    labels = [item.label for item in app.expander]
    assert 'A股热度 · 逐项核算依据' not in labels
    assert 'A股热度 · 原始输入与逐项核算' in labels
