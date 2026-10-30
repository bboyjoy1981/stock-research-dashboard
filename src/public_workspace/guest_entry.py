"""Authenticated guest rendering boundary; authentication stays in friends_app."""
import streamlit as st
from .adapters import from_published
from .contracts import PublicCapabilities
from .navigation import PublicNavigation
from .registry import PAGES,render_page
from .styles import render_workspace_styles


def render_guest_menu():
    state=st.session_state
    page=state.get('guest_page',PAGES[0])
    if page not in PAGES: page=PAGES[0]
    state['guest_page']=page
    core=['市场总览','大盘云图','板块细分','个股详情']
    more=[name for name in PAGES if name not in core]
    for key,options in [('guest_core_menu',core),('guest_more_menu',more)]:
        state[key]=page if page in options else None
    def selected(key):
        value=state.get(key)
        if value in PAGES: state['guest_page']=value
    st.sidebar.title('TradingAgents')
    st.sidebar.caption('A股科技投资研究与决策')
    st.sidebar.subheader('核心市场工作台')
    st.sidebar.caption('市场总览 → 大盘云图 → 个股详情')
    context=state.get('guest_research_context',{})
    industry=str(context.get('industry') or '').strip() if isinstance(context,dict) else ''
    if industry:
        st.sidebar.caption(f"当前研究路径：{context.get('source') or '市场研究'} → {industry}")
        st.sidebar.button('清除当前研究路径',icon=':material/close:',
                          key='guest_sidebar_clear_research_path',on_click=clear_research_path)
    st.sidebar.radio('核心市场研究导航',core,index=None,key='guest_core_menu',
                     on_change=selected,args=('guest_core_menu',),label_visibility='collapsed')
    with st.sidebar.expander('更多市场研究',expanded=False):
        st.radio('更多市场研究导航',more,index=None,key='guest_more_menu',
                 on_change=selected,args=('guest_more_menu',),label_visibility='collapsed')
    return state['guest_page']


def clear_research_path():
    state=st.session_state
    for key in ('research_context','sector','sector_field','sector_parent'):
        state.pop('guest_'+key,None)
    state['guest_sector_revision']=state.get('guest_sector_revision',0)+1
    state['guest_terminal_industry_query']=''
    state['guest_terminal_drilldown_context']=''
    state['guest_terminal_quick_group']='全市场'


def select_published_snapshot(page,data,current):
    if page not in {'市场总览','大盘云图','板块细分','个股详情','盘中选股'}:
        return current
    previous=data.get('previous')
    try:
        prior=from_published(previous) if isinstance(previous,dict) else None
    except (ValueError,TypeError,KeyError):
        prior=None
    if prior is None or prior.metadata['date']>=current.metadata['date']:
        return current
    # Only independently published snapshots are replayable. Never attach current
    # news, temperature, pools or indices to an older stock observation.
    options=['当前快照',prior.metadata['date']]
    if st.session_state.get('guest_market_replay_date') not in options:
        st.session_state['guest_market_replay_date']='当前快照'
    selected=st.sidebar.selectbox('盘后快照交易日',options,key='guest_market_replay_date',
        help='仅列出已发布快照；历史日期使用其自身行情，不以当前数据补齐缺口。')
    return prior if selected==prior.metadata['date'] else current


def render_guest_page(page,data):
    if page not in PAGES:
        st.error('该页面不在公开权限范围内。')
        return
    try:
        snapshot=from_published(data)
    except (ValueError,TypeError,KeyError):
        st.warning('公开快照不可用；请管理员核实独立发布数据。')
        return
    navigation=PublicNavigation('guest',PAGES,st.session_state)
    snapshot=select_published_snapshot(page,data,snapshot)
    st.sidebar.caption('当前快照：'+snapshot.metadata['date'])
    render_workspace_styles()
    if data.get('optional_gaps'):
        st.warning('部分已发布研究数据暂不可用，相关页面保留数据缺口；当前行情快照仍可使用。')
    with st.container(border=True,key='guest_snapshot_header'):
        st.caption(f"公开快照 · {snapshot.metadata['date']} · {len(snapshot.stocks):,}只股票 · 非实时行情")
        st.caption('数据来源与覆盖范围：'+snapshot.metadata['source'])
    render_market_toolbar(page,navigation)
    render_page(page,snapshot,PublicCapabilities(),navigation)


def render_market_toolbar(active,navigation):
    """Original market shortcuts and session-only stock lookup, in the guest namespace."""
    state=navigation.state
    prefix=navigation.namespace+'_'
    routes=[('市场总览','市场总览','dashboard'),('大盘云图','大盘云图','account_tree'),
            ('个股详情','个股详情','query_stats'),('板块资金流向','板块资金流向','swap_vert'),
            ('热点资讯','热点舆情','newspaper'),('盘中选股','盘中选股','filter_alt')]
    def search(code=None):
        query=code or str(state.get(prefix+'workspace_stock_query','')).strip()
        if not query: return
        state.pop(prefix+'research_context',None)
        state[prefix+'terminal_industry_query']=''
        state[prefix+'terminal_drilldown_context']=''
        state[prefix+'terminal_quick_group']='全市场'
        state[prefix+'stock_detail_query']=query
        state.pop(prefix+'stock_detail_selection',None)
        state.pop(prefix+'code',None)
        navigation.open_page('个股详情')
    with st.container(horizontal=True):
        for label,page,icon in routes:
            st.button(label,icon=f':material/{icon}:',key=prefix+'workspace_route_'+page,
                      type='primary' if active==page else 'secondary',
                      on_click=navigation.open_page,args=(page,))
        if active in {'市场总览','大盘云图'}:
            st.text_input('全市场个股搜索',placeholder='股票代码或名称',
                          key=prefix+'workspace_stock_query',label_visibility='collapsed',
                          width=200,on_change=search)
            st.button('查看个股',icon=':material/search:',key=prefix+'workspace_search_submit',on_click=search)
    recent=state.get(prefix+'recent_research_stocks',[])
    if recent:
        with st.expander('最近查看个股',expanded=False):
            st.caption('仅保留本次会话最近 8 只；打开时沿用当前快照日期，不代表自选或交易建议。')
            if active!='个股详情':
                st.button('清空最近查看',icon=':material/clear_all:',key=prefix+'clear_recent_research',
                          on_click=lambda:state.__setitem__(prefix+'recent_research_stocks',[]),
                          help='仅清空本次会话的查看记录，不删除股票池、历史快照或研究数据。')
            with st.container(horizontal=True):
                for item in recent:
                    st.button(f"{item['name']} · {item['code']}",key=prefix+'recent_stock_'+item['code'],
                              on_click=search,args=(item['code'],))
