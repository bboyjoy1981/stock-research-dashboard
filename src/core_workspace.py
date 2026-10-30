"""Shared snapshot provenance and exact industry drill-down for core pages."""
import datetime as dt
import pandas as pd
import streamlit as st


def quote_export(frame, data):
    from .public_workspace.detail_model import quote_export as shared
    return shared(frame,data)


def snapshot_status(data, today=None):
    stocks = data.get('stocks', pd.DataFrame())
    changes = pd.to_numeric(stocks.get('涨跌幅', pd.Series(dtype=float)), errors='coerce')
    rows, valid = len(stocks), int(changes.notna().sum())
    date = str(data.get('import_date') or '未识别')
    try:
        age = ((today or dt.date.today()) - dt.date.fromisoformat(date)).days
    except ValueError:
        age = None
    return {'rows': rows, 'valid': valid, 'unknown': rows - valid,
            'coverage': valid / rows if rows else 0, 'date': date, 'age': age,
            'source': {'imported': '导入快照', 'demo': '演示数据'}.get(data.get('stock_quote_source'), '来源未识别')}


def render_snapshot_strip(data):
    status = snapshot_status(data)
    with st.container(horizontal=True, vertical_alignment='center'):
        st.badge(status['source'], color='blue' if status['source'] == '导入快照' else 'orange')
        st.caption(f"交易日 {status['date']} · 有效涨跌 {status['valid']:,}/{status['rows']:,} · 覆盖 {status['coverage']:.1%} · 非实时")
        if status['age'] is not None and status['age'] > 3:
            st.badge(f"历史快照 · 距今 {status['age']} 天", color='orange')


def filter_map_scope(frame, selections):
    from .public_workspace.cloud_model import filter_map_scope as shared
    return shared(frame,selections)


def reset_cloud_scope():
    st.session_state['core_cloud_parent'] = '全部'
    st.session_state['core_cloud_group'] = '全部'
    st.session_state.pop('core_cloud_stock', None)


def open_full_cloud():
    reset_cloud_scope()
    selected_area = st.session_state.get('overview_map_area')
    if selected_area in {'总市值', '流通市值', '成交额'}:
        st.session_state['terminal_size'] = selected_area
    selected_hierarchy = st.session_state.get('overview_map_hierarchy')
    if selected_hierarchy in {'细分行业', '行业', '板块'}:
        st.session_state['terminal_level'] = selected_hierarchy
    st.session_state['terminal_industry_query'] = ''
    st.session_state['terminal_quick_group'] = '全市场'
    st.session_state.pop('research_context', None)
    st.session_state['terminal_workspace_mode'] = '一屏云图'
    st.session_state['active_nav'] = '大盘云图'


def render_overview_map(stocks,hierarchy,size_field):
    from .closing_report import owner_overview_panels
    return owner_overview_panels(dict(stocks=stocks)).render_overview_map(stocks,hierarchy,size_field)


def owner_cloud_navigation():
    """Owner entry bridge; never imported by the guest renderers."""
    from .public_workspace.navigation import PublicNavigation
    class OwnerCloudNavigation(PublicNavigation):
        def open_page(self,page):
            if not super().open_page(page): return False
            self.state['active_nav']=page
            return True
        def open_stock(self,code,allowed_codes,industry=None,parent=None):
            if not super().open_stock(code,allowed_codes,industry,parent): return False
            open_core_stock(code,industry)
            return True
        def focus_sector(self,field,value,allowed_pairs,parent=None):
            if not super().focus_sector(field,value,allowed_pairs,parent): return False
            from .sector_lens import open_sector_cloud
            open_sector_cloud(field,value,parent if field=='细分行业' else None)
            return True
    return OwnerCloudNavigation('owner',('市场总览','大盘云图','个股详情','板块资金流向','热点舆情'),st.session_state)

def render_exact_cloud_scope(grouped,hierarchy,parent=None):
    from .public_workspace.pages.cloud_components import render_exact_cloud_scope as shared
    from .public_workspace.contracts import PublicCapabilities
    return shared(grouped,hierarchy,parent,PublicCapabilities(download=True),owner_cloud_navigation())


def open_core_stock(label, industry=None, source='大盘云图 · 成分股'):
    st.session_state['stock_detail_query'] = str(label).split(' · ', 1)[0]
    st.session_state.pop('stock_detail_selection', None)
    # A new stock must not inherit an unrelated previous sector path.
    st.session_state.pop('research_context', None)
    if industry is not None and pd.notna(industry):
        industry = str(industry).strip()
        if industry and industry not in {'全部', '未分类', '未细分'}:
            st.session_state['research_context'] = {'source': source, 'industry': industry}
    st.session_state['active_nav'] = '个股详情'


def render_cloud_components(leaves,hierarchy,size_field):
    from .public_workspace.pages.cloud_components import render_cloud_components as shared
    from .public_workspace.contracts import PublicCapabilities
    return shared(leaves,hierarchy,size_field,PublicCapabilities(download=True),owner_cloud_navigation())
