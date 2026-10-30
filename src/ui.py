import streamlit as st


def _clear_research_path():
    from .core_workspace import reset_cloud_scope
    reset_cloud_scope()
    st.session_state.pop("research_context", None)
    st.session_state["terminal_industry_query"] = ""
    st.session_state["terminal_drilldown_context"] = ""
    st.session_state["terminal_quick_group"] = "全市场"


def configure_page():
    st.set_page_config(page_title="A股科技决策看板", page_icon="📊", layout="wide")
    from .public_workspace.styles import render_workspace_styles
    render_workspace_styles()


def render_sidebar(pages):
    st.sidebar.title("TradingAgents")
    st.sidebar.caption("A股科技投资研究与决策")
    core_market_pages = ["市场总览", "大盘云图", "板块细分", "个股详情"]
    other_market_pages = ["板块资金流向", "指数分析", "概念排行", "盘中选股", "板块热力图", "产业链分层", "热点舆情", "数据导入"]
    market_pages = core_market_pages + other_market_pages
    personal_pages = ["决策驾驶舱", "赛博交易舱", "我的交易模型", "持仓管理", "交易计划与复盘", "我的股票池", "报告中心"]
    if "active_nav" not in st.session_state:
        st.session_state["active_nav"] = "赛博交易舱" if st.query_params.get("cyber") == "1" else "市场总览"
    if st.session_state["active_nav"] == "资金回放":
        st.session_state["active_nav"] = "板块资金流向"

    def choose_core_market():
        st.session_state["active_nav"] = st.session_state["market_nav"]

    def choose_more_market():
        st.session_state["active_nav"] = st.session_state["more_market_nav"]

    def choose_personal():
        st.session_state["active_nav"] = st.session_state["personal_nav"]

    active = st.session_state["active_nav"]
    if active == "赛博交易舱":
        if st.query_params.get("cyber") != "1":
            st.query_params["cyber"] = "1"
    elif "cyber" in st.query_params:
        del st.query_params["cyber"]
    # Synchronize before rendering widgets, including navigation from peer cards.
    for key, options in [("market_nav", core_market_pages), ("more_market_nav", other_market_pages), ("personal_nav", personal_pages)]:
        st.session_state[key] = active if active in options else None
    st.sidebar.subheader("核心市场工作台")
    st.sidebar.caption("市场总览 → 大盘云图 → 个股详情")
    research_context = st.session_state.get("research_context", {})
    research_industry = str(research_context.get("industry") or "").strip() if isinstance(research_context, dict) else ""
    if research_industry:
        source = str(research_context.get("source") or "市场研究").strip()
        st.sidebar.caption(f"当前研究路径：{source} → {research_industry}")
        st.sidebar.button(
            "清除当前研究路径",
            icon=":material/close:",
            key="sidebar_clear_research_path",
            on_click=_clear_research_path,
        )
    st.sidebar.radio(
        "核心市场研究导航", core_market_pages,
        index=None,
        key="market_nav", on_change=choose_core_market, label_visibility="collapsed",
    )
    with st.sidebar.expander("更多市场研究", expanded=False):
        st.radio(
            "更多市场研究导航", other_market_pages,
            index=None,
            key="more_market_nav", on_change=choose_more_market, label_visibility="collapsed",
        )
    st.sidebar.subheader("个人决策")
    st.sidebar.radio(
        "个人决策导航", personal_pages,
        index=None,
        key="personal_nav", on_change=choose_personal, label_visibility="collapsed",
    )
    return st.session_state["active_nav"]


def _open_market_workspace(page):
    st.session_state["active_nav"] = page
    if page in {"市场总览", "大盘云图", "个股详情"}:
        st.session_state["market_nav"] = page
    else:
        st.session_state["more_market_nav"] = page


def _search_market_stock():
    query = str(st.session_state.get("workspace_stock_query", "")).strip()
    if query:
        _clear_research_path()
        st.session_state["stock_detail_query"] = query
        st.session_state.pop("stock_detail_selection", None)
        _open_market_workspace("个股详情")


def _open_recent_stock(code):
    _clear_research_path()
    st.session_state["stock_detail_query"] = code
    st.session_state.pop("stock_detail_selection", None)
    _open_market_workspace("个股详情")


def _clear_recent_research():
    st.session_state['recent_research_stocks'] = []


def render_market_workspace_toolbar(active, data=None):
    """Keep the main research routes and stock lookup within reach."""
    routes = [
        ("市场总览", "市场总览", "dashboard"),
        ("大盘云图", "大盘云图", "account_tree"),
        ("个股详情", "个股详情", "query_stats"),
        ("板块资金流向", "板块资金流向", "swap_vert"),
        ("热点资讯", "热点舆情", "newspaper"),
        ("盘中选股", "盘中选股", "filter_alt"),
    ]
    if data is not None and active in {"市场总览", "大盘云图", "个股详情"}:
        from .core_workspace import render_snapshot_strip
        render_snapshot_strip(data)
    with st.container(horizontal=True):
        for label, page, icon in routes:
            st.button(
                label, icon=f":material/{icon}:",
                key=f"workspace_route_{page}",
                type="primary" if active == page else "secondary",
                on_click=_open_market_workspace, args=(page,),
            )
        if active in {"市场总览", "大盘云图"}:
            st.text_input("全市场个股搜索", placeholder="股票代码或名称",
                          key="workspace_stock_query", label_visibility="collapsed", width=200,
                          on_change=_search_market_stock)
            st.button("查看个股", icon=":material/search:",
                      key="workspace_search_submit", on_click=_search_market_stock)
    recent = st.session_state.get("recent_research_stocks", [])
    if recent:
        with st.expander("最近查看个股", expanded=False):
            st.caption("仅保留本次会话最近 8 只；打开时沿用当前快照日期，不代表自选或交易建议。")
            if active != '个股详情':
                st.button('清空最近查看', icon=':material/clear_all:',
                          key='clear_recent_research', on_click=_clear_recent_research,
                          help='仅清空本次会话的查看记录，不删除股票池、历史快照或研究数据。')
            with st.container(horizontal=True):
                for item in recent:
                    st.button(
                        f"{item['name']} · {item['code']}", key=f"recent_stock_{item['code']}",
                        on_click=_open_recent_stock, args=(item['code'],),
                    )


def render_metric_card(label, value, caption="", tone="normal"):
    st.metric(label, value, caption)
