"""Compact, auditable market-environment view using native Streamlit UI."""

from pathlib import Path
import json
import hashlib
import os
import tempfile

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

from src.price_limits import confirmed_limit_counts
from src.temperature_data import observations_at
from src.temperature_rules import GROUPS, METRICS, compare_temperature, evaluate_temperature
from src.temperature_sources import PENDING_SOURCES, RELEASES, collect_temperature_sources
from src.temperature_store import load_observations, save_observations
from src.temperature_stage import evaluate_trend_stage
from src.temperature_refresh import refresh_latest_sources
from src.temperature_snapshot_audit import audit_imported_snapshots

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / 'data' / 'temperature'
from .public_workspace.temperature_model import INDICATOR_GROUP
from .public_workspace.temperature_model import INDICATOR_NAMES


@st.cache_data(max_entries=8, show_spinner=False)
def _evaluate(frame, cutoff):
    return evaluate_temperature(frame, cutoff)


@st.cache_data(max_entries=8, show_spinner=False)
def _stage(frame, cutoff):
    return evaluate_trend_stage(frame, cutoff)


def _latest_cutoff(data, frame, now=None):
    view=_temperature_view(prepare=False)
    return view._latest_cutoff(data,frame,now)


def _latest_overall_reference(data):
    """Evaluate latest captured inputs without backdating them into replay."""
    frame = load_observations(Path(data.get('temperature_directory', DEFAULT_DIRECTORY)) / 'latest')
    cutoff = _latest_cutoff(data, frame)
    macro_mask = frame['indicator_id'].map(INDICATOR_GROUP).eq('宏观环境')
    macro = frame.loc[macro_mask]
    if not macro.empty:
        from src.temperature_alignment import align_macro_history
        macro, _ = align_macro_history(macro, cutoff)
    latest = pd.concat([macro, frame.loc[~macro_mask]], ignore_index=True)
    from src.temperature_alignment import align_shared_daily_history
    latest, _ = align_shared_daily_history(latest, cutoff, ('sp500', 'nasdaq'))
    return _evaluate(latest, cutoff), cutoff


def _last_complete_reference(data, current=None):
    """Keep the last fully covered research result with its original cutoff."""
    directory = Path(data.get('temperature_directory', DEFAULT_DIRECTORY))
    path = directory / 'last_complete_result.json'
    try:
        saved = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    except (OSError, ValueError, TypeError):
        saved = None
    if current is None:
        return saved
    result, cutoff = current
    if result['internal_score'] is None or result['coverage'] < 100:
        return saved
    signature = hashlib.sha256(repr(result['input_signature']).encode('utf-8')).hexdigest()
    if (saved and saved.get('input_signature') == signature
            and saved.get('score') == result['internal_score']
            and saved.get('label') == result['label']):
        return saved
    complete = dict(label=result['label'], score=result['internal_score'],
                    coverage=result['coverage'], cutoff=cutoff.isoformat(),
                    input_signature=signature)
    temporary = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=directory,
                                         prefix='.last_complete_', suffix='.json',
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(complete, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return complete


def _render_latest_overall_reference(data):
    view=_temperature_view(data)
    return view._render_latest_overall_reference(view.data)


def _trend_reference(data):
    """Post-capture diagnostic, never backdate captured data into the replay."""
    try:
        frame = load_observations(Path(data.get('temperature_directory', DEFAULT_DIRECTORY)) / 'latest')
        frame = frame.loc[frame['data_period'].le(str(data.get('import_date', '')))]
        cutoff = _latest_cutoff(data, frame)
        result = _stage(frame, cutoff)
        result['reference_basis'] = '最新捕获历史的事后参考，非原始发布时点回测'
        return result
    except (OSError, ValueError, TypeError):
        return dict(label='待补指数历史', indices=[], technology='待补科技指数历史',
                    annual_line=dict(level=None, status='数据读取或校验失败'))


def _render_trend_details(data):
    view=_temperature_view(data)
    return view._render_trend_details(view.data)


def _fact_table(frame):
    view=_temperature_view(prepare=False)
    return view._fact_table(frame)


def _local_snapshot_facts(data):
    view=_temperature_view(data)
    return view._local_snapshot_facts(view.data)


def temperature_weight_chart():
    view=_temperature_view(prepare=False)
    return view.temperature_weight_chart()


def _render_temperature_headline(result, comparison, container=None, latest_reference=None,
                                 replay_day=None, last_complete=None):
    view=_temperature_view(prepare=False)
    return view._render_temperature_headline(result,comparison,container,latest_reference,replay_day,last_complete)


def _render_commodity_quotes():
    view=_temperature_view()
    return view._render_commodity_quotes()


def _render_environment_facts():
    view=_temperature_view()
    return view._render_environment_facts()


def _render_latest_overseas(data):
    view=_temperature_view(data)
    return view._render_latest_overseas(view.data)


def _render_latest_research(data, group_name):
    view=_temperature_view(data)
    return view._render_latest_research(view.data,group_name)


def _render_historical_comparisons(frame, cutoff):
    view=_temperature_view(prepare=False)
    return view._render_historical_comparisons(frame,cutoff)


def _render_comparison_explanations(frame, cutoff, names):
    view=_temperature_view(prepare=False)
    return view._render_comparison_explanations(frame,cutoff,names)


def _conclusion_badge(label):
    view=_temperature_view(prepare=False)
    return view._conclusion_badge(label)


def _render_time_basis(group, result, cutoff_text):
    view=_temperature_view(prepare=False)
    return view._render_time_basis(group,result,cutoff_text)


def _input_catalog(fresh, group=None):
    view=_temperature_view(prepare=False)
    return view._input_catalog(fresh,group)


@st.dialog('市场温度 · 研究详情', width='large',
           on_dismiss=lambda: st.session_state.update(temperature_details_open=False))
def _render_temperature_details(data: dict) -> None:
    view=_temperature_view(data)
    return view._render_temperature_details(view.data)


def _owner_temperature_inputs(data):
    """Authorized owner data adapter; no website renderer imports this module."""
    prepared=dict(data)
    directory=Path(data.get('temperature_directory',DEFAULT_DIRECTORY))
    for key,folder in (('temperature_stored_observations',directory),
                       ('temperature_latest_observations',directory/'latest'),
                       ('temperature_comparison_observations',directory/'comparison')):
        try:
            prepared[key]=load_observations(folder)
        except (OSError,ValueError,TypeError):
            from .temperature_data import validate_observations
            prepared[key]=validate_observations(pd.DataFrame())
            prepared[key+'_error']=True
    for key,filename in (('temperature_environment_review','environment_review.json'),
                         ('temperature_commodity_review','commodity_review.json'),
                         ('temperature_last_complete','last_complete_result.json')):
        try:
            folder=directory if key=='temperature_last_complete' else DEFAULT_DIRECTORY
            path=folder/filename
            prepared[key]=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        except (OSError,ValueError,TypeError):
            prepared[key]=None
    try:
        prepared['temperature_import_audit']=audit_imported_snapshots(DEFAULT_DIRECTORY.parent/'imports')
    except (OSError,ValueError,TypeError):
        prepared['temperature_import_audit']=pd.DataFrame()
    return prepared


def _owner_temperature_update_ui(data,cutoff):
    directory=Path(data.get('temperature_directory',DEFAULT_DIRECTORY))
    supplied=data.get('temperature_observations',pd.DataFrame())
    observations=pd.concat([data.get('temperature_stored_observations',pd.DataFrame()),supplied],ignore_index=True)
    errors=[]
    # All remote work is gated by an explicit action, not app reruns.
    if st.button('更新市场环境数据', icon=':material/refresh:', key='update_market_temperature',
                 help='按需更新已接通的发布页及宏观、海外历史；最新研究与所选复盘分开保存，不创建后台任务。'):
        st.session_state['temperature_source_status'] = []
        st.session_state['temperature_update_errors'] = []
        try:
            with st.spinner('核验公开发布数据…'):
                update = collect_temperature_sources(cutoff)
                save_observations(update['observations'], directory)
                save_observations(update['observations'], directory / 'latest')
                observations = pd.concat([load_observations(directory), supplied], ignore_index=True)
            st.session_state['temperature_source_status'] = update['source_status']
            st.session_state['temperature_update_errors'] = update['errors']
            st.session_state['temperature_updated_at'] = update['fetched_at']
            if not update['observations'].empty:
                st.caption(f"本次取得{len(update['observations'])}条原始观测；不代表历史覆盖已满足。")
        except (OSError, ValueError, KeyError) as error:
            errors.append(f'更新失败，保留已有数据：{error}')
        try:
            with st.spinner('更新最新研究历史：宏观、海外指数、A股指数、交易所成交与两融…'):
                latest = refresh_latest_sources(directory / 'latest', include_ashare=True)
            st.session_state['temperature_source_status'].extend(latest['source_status'])
            st.session_state['temperature_update_errors'].extend(latest['errors'])
            st.session_state['temperature_updated_at'] = latest['fetched_at']
            st.caption(f"最新研究本次保存{latest['saved_count']}条历史观测；不覆盖所选历史复盘，不代表全部指标已接通。")
        except (OSError, ValueError, KeyError) as error:
            errors.append(f'最新研究更新失败，保留已有数据：{error}')
    data.update(_owner_temperature_inputs(data))
    for error in errors: st.warning(error)
    return observations


def _temperature_view(data=None,prepare=True):
    from .public_workspace.pages.temperature import TemperatureView
    from .public_workspace.contracts import PublicCapabilities
    from .public_workspace.navigation import PublicNavigation
    supplied=_owner_temperature_inputs(data or {}) if prepare else (data or {})
    return TemperatureView(supplied,PublicCapabilities(download=True),PublicNavigation('owner',('市场总览',),st.session_state),
                           prefix='',owner_update_ui=_owner_temperature_update_ui)


def render_market_temperature(data: dict, headline_container=None) -> None:
    view=_temperature_view(data)
    try:
        latest_reference=_latest_overall_reference(data)
    except (OSError,ValueError,TypeError):
        latest_reference=None
    view.data['temperature_last_complete']=_last_complete_reference(data,latest_reference)
    return view.render_market_temperature(view.data,headline_container)
