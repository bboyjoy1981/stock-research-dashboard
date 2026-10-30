import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import json
from datetime import datetime, time as datetime_time
from pathlib import Path
import tempfile
from .importers import (
    import_quality_report,
    select_market_group_column,
    market_map_hierarchy_path,
    market_group_display_mask,
    market_group_coverage,
    market_navigation_level,
    researchable_market_groups,
    valid_peer_group_fields,
    capital_replay_template,
    capital_replay_industry_track,
    capital_replay_flow_changes,
    capital_replay_readiness,
    filter_capital_replay_by_date,
    capital_replay_snapshot_map,
    load_capital_replay,
    normalize_capital_replay,
    read_tabular_upload,
    save_capital_replay,
    validate_capital_replay,
)
from .calculations import compare_stock_pool, market_component_extremes, market_map_leaves, market_map_area_options, limit_market_map_leaves, sector_rotation_board, stock_relative_snapshot, index_pulse_snapshot, market_sector_tiers, industry_chain_summary, market_close_review, market_overview_radar, market_research_queue, market_activity_concentration, market_snapshot_trend, market_change_distribution, market_overview_distribution, market_close_temperature, market_history_coverage, market_trend_summary, research_context_label, filter_stocks_by_research_context, stock_snapshot_history, market_sector_turnover
from .storage import save_theme_snapshot, list_theme_snapshots, save_market_snapshot, list_market_snapshots
from .core_workspace import quote_export
from .price_limits import confirmed_limit_counts

DB_PATH = str(Path(__file__).resolve().parent.parent / "decision.db")


def _ashare_change_style(frame: pd.DataFrame, fields=("涨跌幅",)):
    from .public_workspace.detail_model import _ashare_change_style as shared
    return shared(frame,fields)


def _clear_terminal_industry_context():
    from .core_workspace import reset_cloud_scope
    reset_cloud_scope()
    st.session_state["terminal_industry_query"] = ""
    st.session_state["terminal_drilldown_context"] = ""
    st.session_state["terminal_quick_group"] = "全市场"
    st.session_state.pop("research_context", None)


def _set_terminal_research_context(industry, source="大盘云图 · 市场脉冲"):
    """Focus the next terminal rerun on a selected research industry."""
    target = str(industry).strip()
    if not target:
        return
    from .core_workspace import reset_cloud_scope
    reset_cloud_scope()
    st.session_state["terminal_industry_query"] = target
    st.session_state["research_context"] = {"source": source, "industry": target}


def _open_research_path(target):
    context = st.session_state.get("research_context", {})
    if target == "大盘云图":
        from .core_workspace import reset_cloud_scope
        reset_cloud_scope()
        st.session_state["terminal_industry_query"] = str(context.get("industry", "")).strip()
        st.session_state["terminal_workspace_mode"] = "一屏云图"
    elif target == "个股详情":
        st.session_state["stock_detail_query"] = ""
        st.session_state.pop("stock_detail_selection", None)
    st.session_state["active_nav"] = target


def _render_research_context(key):
    """Keep the selected industry visible while users move between research views."""
    label = research_context_label(st.session_state.get("research_context", {}))
    if not label:
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.info(label, icon=":material/route:")
        st.button("定位云图", icon=":material/account_tree:", key=f"research_path_cloud_{key}",
                  on_click=_open_research_path, args=("大盘云图",))
        st.button("查看同业", icon=":material/query_stats:", key=f"research_path_peers_{key}",
                  on_click=_open_research_path, args=("个股详情",))
        st.button("清除路径", icon=":material/close:", key=f"clear_research_context_{key}",
                  on_click=_clear_terminal_industry_context)


def _snapshot_as_of_label(data):
    trade_date = data.get("import_date")
    return f"截至交易日：{trade_date}" if trade_date else "截至交易日：未识别（请在导出文件中保留交易日期列）"


def _china_market_session(now=None):
    """Return whether the local Shanghai clock is inside an A-share session."""
    current = now or datetime.now()
    if current.weekday() >= 5:
        return False
    clock = current.time()
    return datetime_time(9, 30) <= clock <= datetime_time(11, 30) or datetime_time(13, 0) <= clock <= datetime_time(15, 5)


def _capital_flow_capture_bucket(now):
    """Return the five-minute bucket containing ``now`` for capture deduplication."""
    bucket_minute = now.minute - now.minute % 5
    return now.replace(minute=bucket_minute, second=0, microsecond=0).strftime("%Y%m%d%H%M")


def _collect_capital_flow_snapshot(replay_dir, *, persist=True):
    """Try the current provider first, then switch sources only on failure."""
    from .capital_flow_source import fetch_capital_flow_snapshot_with_diagnostics

    st.session_state.pop("capital_flow_capture_diagnostics", None)
    st.session_state.pop("capital_flow_source_switch", None)
    try:
        previous = load_capital_replay(replay_dir)
        preferred_provider = None
        if {"时间", "数据来源"}.issubset(previous.columns):
            today = datetime.now().strftime("%Y-%m-%d")
            same_day = previous.loc[previous["时间"].astype(str).str.startswith(today)].sort_values("时间")
            sources = same_day["数据来源"].dropna().astype(str)
            if not sources.empty:
                latest_source = sources.iloc[-1]
                preferred_provider = next(
                    (provider for provider in ("东方财富", "同花顺") if latest_source.startswith(provider)), None
                )
        providers = [preferred_provider or "东方财富"]
        providers.append("同花顺" if providers[0] == "东方财富" else "东方财富")
        source_errors = []
        for index, provider in enumerate(providers):
            try:
                result = fetch_capital_flow_snapshot_with_diagnostics(preferred_provider=provider)
                frame = result["snapshot"]
                diagnostics = result["diagnostics"]
                st.session_state["capital_flow_capture_diagnostics"] = diagnostics.to_dict("records")
                st.session_state["capital_flow_capture_diagnostics_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                failed_sources = diagnostics.loc[
                    diagnostics["状态"].isin(("来源获取失败", "部分来源获取失败")), "行业"
                ].drop_duplicates().tolist()
                if failed_sources:
                    raise ValueError("行业或概念排行未完整获取；缺失板块：" + "、".join(failed_sources))
                if frame.empty:
                    raise ValueError("没有匹配到关注板块；请查看最近一次采集诊断")
                missing_sectors = sorted(set(CAPITAL_FLOW_SECTORS) - set(frame["行业"]))
                if missing_sectors or frame["净流入额"].isna().any():
                    raise ValueError("目标板块数据不完整：" + "、".join(missing_sectors))
                if index:
                    st.session_state["capital_flow_source_switch"] = (
                        f"{providers[0]}采集失败，已切换到{provider}；不同资金源的走势分段显示。"
                    )
                if not persist:
                    return frame, None, None
                path = save_capital_replay(frame, replay_dir)
                return frame, path, None
            except Exception as exc:
                source_errors.append(f"{provider}: {str(exc).replace(chr(10), ' ')[:180]}")
        return None, None, "两个资金源均不可用；" + "；".join(source_errors)
    except Exception as exc:
        message = str(exc).replace("\n", " ").strip()
        if (isinstance(exc, ConnectionError) or "AKShare 与东方财富备用接口均连接失败" in message
                or "HTTPS_PROXY" in message or "proxy" in message.lower() or "TLS" in message):
            detail = message or exc.__class__.__name__
            if len(detail) > 480:
                detail = detail[:477] + "..."
            return None, None, f"资金源连接失败：{detail}"
        if len(message) > 240:
            message = message[:237] + "..."
        return None, None, message or exc.__class__.__name__


def _capital_flow_video_unavailable_reason(day_replay, selected_sectors):
    if not selected_sectors:
        return "先选择至少一个板块。"
    if not {"时间", "行业", "净流入额"}.issubset(day_replay.columns):
        return "当前日期没有可用的资金快照。"
    frame = day_replay.loc[:, ["时间", "行业", "净流入额"]].copy()
    frame["时间戳"] = pd.to_datetime(frame["时间"], errors="coerce")
    frame["净流入额"] = pd.to_numeric(frame["净流入额"], errors="coerce")
    frame = frame.dropna(subset=["时间戳", "净流入额"])
    minute_of_day = frame["时间戳"].dt.hour * 60 + frame["时间戳"].dt.minute
    in_session = (
        frame["时间戳"].dt.weekday.lt(5)
        & (minute_of_day.between(9 * 60 + 30, 11 * 60 + 30)
           | minute_of_day.between(13 * 60, 15 * 60))
    )
    frame = frame.loc[in_session]
    frame = frame.loc[frame["行业"].astype(str).isin(selected_sectors)]
    if frame.empty:
        return "所选板块在这一天没有交易时段内的有效快照。"
    if frame["时间戳"].nunique() < 2:
        return "所选板块至少需要两个交易时点才能生成全天视频。"
    return None


def _render_capital_flow_video_export(day_replay, selected_sectors, trade_date):
    """Offer an MP4 made from the currently displayed day and sector selection."""
    with st.container(border=True):
        st.subheader("全天走势视频", icon=":material/movie:")
        unavailable_reason = _capital_flow_video_unavailable_reason(day_replay, selected_sectors)
        columns = [column for column in ("时间", "行业", "净流入额") if column in day_replay.columns]
        fingerprint = int(pd.util.hash_pandas_object(day_replay[columns], index=False).sum()) if columns else 0
        signature = (str(trade_date), tuple(selected_sectors), len(day_replay), fingerprint)
        artifact = st.session_state.get("capital_flow_video_artifact")
        if artifact and artifact.get("signature") != signature:
            st.session_state.pop("capital_flow_video_artifact", None)
            artifact = None

        if st.button("生成全天走势 MP4", icon=":material/movie:", key="capital_flow_generate_video",
                     disabled=unavailable_reason is not None):
            try:
                from .capital_flow_video import render_capital_flow_video

                with st.spinner("正在按真实采集快照绘制全天走势视频…"):
                    with tempfile.TemporaryDirectory(prefix="capital-flow-video-") as temp_dir:
                        video_path = Path(temp_dir) / f"capital_flow_{trade_date}.mp4"
                        metadata = render_capital_flow_video(
                            day_replay=day_replay,
                            sectors=list(selected_sectors),
                            output_path=video_path,
                        )
                        video_bytes = video_path.read_bytes()
                artifact = {"signature": signature, "bytes": video_bytes, "metadata": metadata}
                st.session_state["capital_flow_video_artifact"] = artifact
            except Exception as exc:
                st.error(f"视频生成失败：{str(exc)}")
                artifact = None

        if unavailable_reason:
            st.caption(unavailable_reason)
        if artifact and artifact.get("signature") == signature:
            metadata = artifact["metadata"]
            st.caption(
                f"{metadata['snapshot_count']} 个真实采集时点｜{metadata['first_time']}—{metadata['last_time']}｜"
                f"约 {metadata['duration_seconds']:.0f} 秒；午休已压缩，没有补造数据。"
            )
            if metadata["missing_sectors"]:
                st.caption("最后时点缺少数据：" + "、".join(metadata["missing_sectors"]))
            st.download_button(
                "下载全天走势 MP4",
                data=artifact["bytes"],
                file_name=f"板块资金全天走势_{trade_date}.mp4",
                mime="video/mp4",
                icon=":material/download:",
                key="capital_flow_download_video",
            )


def _capital_replay_segments(day_replay):
    from .public_workspace.capital_model import capital_replay_segments as shared
    return shared(day_replay)


def _render_intraday_flow_charts(day_replay):
    """Owner lifecycle compatibility; charts are shared, video stays owner-only."""
    from .public_workspace.pages.capital import render_flow_charts
    render_flow_charts(day_replay, st.session_state)
    selected=st.session_state.get("capital_flow_selected_sectors",[])
    if not selected or day_replay.empty or not {"时间","行业","净流入额"}.issubset(day_replay):
        return
    segments=_capital_replay_segments(day_replay)
    chosen=st.session_state.get("capital_flow_visible_segment")
    if len(segments)>1:
        day_replay=next((frame for label,frame in segments if label==chosen),segments[-1][1])
    dates=day_replay["时间"].dropna().astype(str).str[:10]
    _render_capital_flow_video_export(day_replay,selected,dates.iloc[0] if not dates.empty else "unknown-date")


def market_quote_origin(data):
    """Describe whether displayed stock quotes are imported or illustrative."""
    if data.get("stock_quote_source") == "imported":
        return f"导入行情快照｜{_snapshot_as_of_label(data)}"
    return "演示行情｜非真实市场报价"


def _focus_overview_industry(target, field):
    industry = st.session_state.get('overview_primary_industry')
    if not industry:
        return
    st.session_state['research_context'] = {'source': '市场总览 · 行业排行', 'industry': industry}
    if target == 'members':
        st.session_state['overview_stock_scope'] = industry
        st.session_state['overview_workspace'] = '行情榜单'
    elif target == 'cloud':
        from .core_workspace import reset_cloud_scope
        reset_cloud_scope()
        st.session_state['terminal_industry_query'] = industry
        st.session_state['terminal_level'] = field
        st.session_state['terminal_workspace_mode'] = '一屏云图'
        st.session_state['active_nav'] = '大盘云图'


def _clear_detail_search():
    _clear_terminal_industry_context()
    st.session_state['stock_detail_query'] = ''
    st.session_state.pop('stock_detail_selection', None)


def _reset_detail_selection():
    st.session_state.pop('stock_detail_selection', None)


def render_demo_index_preview(indices):
    """Keep layout samples opt-in until a real index feed is integrated."""
    st.caption("指数接口尚未接入；此区域不参与导入快照的市场统计。")
    if not st.toggle("查看演示指数布局", value=False, key="overview_show_demo_indices",
                     help="仅用于界面预览，不能作为当天指数行情或复盘依据。"):
        return
    st.caption("演示指数 · 非真实报价 · 不与导入的个股快照进行比较。")
    if indices.empty or not {"名称", "涨跌幅"}.issubset(indices.columns):
        st.info("当前没有可用的指数布局样例。")
        return
    table = indices.loc[:, ~indices.columns.duplicated()].copy()
    table["涨跌幅"] = pd.to_numeric(table["涨跌幅"], errors="coerce")
    columns = [field for field in ("名称", "点位", "涨跌幅") if field in table]
    table = table.dropna(subset=["涨跌幅"]).head(10)[columns]
    st.dataframe(_ashare_change_style(table),
                 column_config={"涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%.2f%%"),
                                "点位": st.column_config.NumberColumn("点位", format="%,.2f")},
                 width="stretch", hide_index=True, height=310)


def render_market_overview(data):
    quality = import_quality_report(data.get("stocks"))
    st.caption(f"\u884c\u60c5\u8986\u76d6\uff1a{quality['valid_quotes']:,}/{quality['rows']:,} \u884c\uff5c" + ("\u53ef\u7528\u4e8e\u5e7f\u5ea6\u5224\u65ad" if quality["quote_ready"] else "\u4ec5\u8eab\u4efd\u6570\u636e"))
    st.title("\u5e02\u573a\u603b\u89c8")
    st.caption("\u6570\u636e\u6765\u6e90\uff1a\u672c\u5730\u5bfc\u5165\u6216\u6f14\u793a\u6570\u636e\uff1b\u4ec5\u4f5c\u7814\u7a76\u53c2\u8003\uff0c\u4e0d\u6784\u6210\u6295\u8d44\u5efa\u8bae")
    status_cols = st.columns(4)
    status_cols[0].metric("数据状态", "已加载" if quality["rows"] else "暂无")
    status_cols[1].metric("行情覆盖", f"{quality['coverage'].get('涨跌幅', 0):.1%}")
    status_cols[2].metric("研究样本", f"{quality['rows']:,} 行")
    status_cols[3].metric("数据类型", "导入快照 / 演示")
    st.caption("本页面基于最近一次导入快照，不是实时行情；如需更新，请前往‘数据导入’重新上传同花顺文件。")
    market_view = st.selectbox("市场视图", ["综合总览", "行业强弱", "成交额活跃", "涨跌结构"], key="market_view")
    st.caption(f"当前视图：{market_view}；下方模块会按统一市场快照展示研究结果。")
    if data.get("source_notice"):
        st.info(data["source_notice"])
    indices, sectors, stocks = data["indices"], data["sectors"], data["stocks"]
    up = int((stocks["\u6da8\u8dcc\u5e45"] > 0).sum())
    down = int((stocks["\u6da8\u8dcc\u5e45"] < 0).sum())
    avg = float(stocks["\u6da8\u8dcc\u5e45"].mean())
    point_col, change_col, name_col = "\u70b9\u4f4d", "\u6da8\u8dcc\u5e45", "\u677f\u5757"
    market_total = max(up + down + int((stocks["\u6da8\u8dcc\u5e45"] == 0).sum()), 1)
    market_strength = max(0, min(100, round(50 + (up - down) / market_total * 50)))
    market_state = "普涨" if up > down * 1.5 else "普跌" if down > up * 1.5 else "结构分化"
    sector_snapshot = sectors.copy()
    if change_col in sector_snapshot.columns:
        sector_snapshot[change_col] = pd.to_numeric(sector_snapshot[change_col], errors="coerce")
    if "成交额" in sector_snapshot.columns:
        sector_snapshot["成交额"] = pd.to_numeric(sector_snapshot["成交额"], errors="coerce").fillna(0)

    with st.container(border=True):
        st.subheader("市场研究驾驶台", icon=":material/dashboard:")
        st.caption("从这里查看市场状态，再进入“大盘云图”定位行业、进入“个股详情”完成同类对比。")
        with st.container(horizontal=True):
            if st.button("进入大盘云图", icon=":material/account_tree:", key="overview_open_terminal"):
                st.session_state["active_nav"] = "大盘云图"
                st.rerun()
            if st.button("进入个股详情", icon=":material/description:", key="overview_open_detail"):
                st.session_state["active_nav"] = "个股详情"
                st.rerun()
        st.badge(market_state, icon=":material/monitoring:", color="green" if market_state == "普涨" else "red" if market_state == "普跌" else "blue")
        with st.container(horizontal=True):
            st.metric("市场强弱", f"{market_strength}/100", border=True)
            st.metric("上涨家数", f"{up:,}", border=True)
            st.metric("下跌家数", f"{down:,}", border=True)
            st.metric("平均涨跌", f"{avg:+.2f}%", border=True)
        overview_left, overview_right = st.columns([1.15, 1], vertical_alignment="top")
        with overview_left:
            if not sector_snapshot.empty and {name_col, change_col}.issubset(sector_snapshot.columns):
                leaders = sector_snapshot.dropna(subset=[change_col]).sort_values(change_col, ascending=False).head(10).sort_values(change_col)
                leader_chart = px.bar(leaders, x=change_col, y=name_col, orientation="h", color=change_col, color_continuous_scale="RdYlGn", color_continuous_midpoint=0)
                leader_chart.update_layout(height=330, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="涨跌幅（%）", yaxis_title="")
                st.plotly_chart(leader_chart, width="stretch")
        with overview_right:
            st.markdown("**市场关注方向**")
            if not sector_snapshot.empty and {name_col, change_col}.issubset(sector_snapshot.columns):
                overview_cols = [field for field in (name_col, change_col, "成交额") if field in sector_snapshot.columns]
                st.dataframe(sector_snapshot.sort_values(change_col, ascending=False).head(10)[overview_cols], column_config={change_col: st.column_config.NumberColumn("涨跌幅", format="%.2f%%"), "成交额": st.column_config.NumberColumn("成交额", format="compact")}, width="stretch", hide_index=True, height=330)
        if {"代码", "名称"}.issubset(stocks.columns):
            focus_pool = stocks.copy()
            if "成交额" in focus_pool.columns:
                focus_pool["成交额"] = pd.to_numeric(focus_pool["成交额"], errors="coerce").fillna(0)
                focus_pool = focus_pool.sort_values("成交额", ascending=False)
            focus_pool = focus_pool.head(80)
            focus_labels = (focus_pool["代码"].astype(str) + " · " + focus_pool["名称"].fillna("未命名").astype(str)).tolist()
            with st.container(horizontal=True, vertical_alignment="bottom"):
                selected_focus = st.selectbox("快速进入个股研究", focus_labels, key="overview_stock_jump")
                if st.button("打开个股详情", icon=":material/open_in_new:", key="overview_open_stock"):
                    st.session_state["stock_detail_query"] = selected_focus.split(" · ", 1)[0]
                    st.session_state["active_nav"] = "个股详情"
                    st.rerun()
        change_values_top = pd.to_numeric(stocks.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
        if not change_values_top.empty:
            structure_left, structure_right = st.columns([1.55, 1], vertical_alignment="top")
            with structure_left:
                st.markdown("**市场涨跌结构**")
                bucket_labels = ["<-5%", "-5~-2%", "-2~0%", "0~2%", "2~5%", ">5%"]
                bucket_values = pd.cut(change_values_top, [-float("inf"), -5, -2, 0, 2, 5, float("inf")], labels=bucket_labels).value_counts().reindex(bucket_labels, fill_value=0)
                st.bar_chart(bucket_values, height=220)
            with structure_right:
                st.markdown("**极端波动观察**")
                st.metric("涨停附近", int((change_values_top >= 9.8).sum()), border=True)
                st.metric("跌停附近", int((change_values_top <= -9.8).sum()), border=True)
                st.caption("以上仅描述导入快照中的涨跌分布，不代表后续走势。")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("\u6caa\u6df1300", f"{indices.iloc[0][point_col]:.2f}", f"{indices.iloc[0][change_col]:+.2f}%")
    c2.metric("\u5e02\u573a\u4e0a\u6da8", up, f"\u4e0b\u8dcc {down}")
    c3.metric("\u5e73\u5747\u6da8\u8dcc", f"{avg:+.2f}%")
    c4.metric("\u5f3a\u52bf\u677f\u5757", str(sectors.sort_values(change_col, ascending=False).iloc[0][name_col]))
    st.subheader("主要指数快照")
    index_cards = indices.head(8).to_dict("records")
    card_row = st.columns(min(4, max(1, len(index_cards))))
    for card, item in zip(card_row, index_cards[:4]):
        point = pd.to_numeric(item.get("点位"), errors="coerce")
        delta = pd.to_numeric(item.get("涨跌幅"), errors="coerce")
        card.metric(str(item.get("名称", "指数")), f"{point:.2f}" if pd.notna(point) else "—", f"{delta:+.2f}%" if pd.notna(delta) else "—")
    if len(index_cards) > 4:
        card_row2 = st.columns(min(4, len(index_cards) - 4))
        for card, item in zip(card_row2, index_cards[4:8]):
            point = pd.to_numeric(item.get("点位"), errors="coerce")
            delta = pd.to_numeric(item.get("涨跌幅"), errors="coerce")
            card.metric(str(item.get("名称", "指数")), f"{point:.2f}" if pd.notna(point) else "—", f"{delta:+.2f}%" if pd.notna(delta) else "—")
    st.subheader("板块强弱速览")
    top_sectors = sectors.sort_values(change_col, ascending=False).head(3)
    weak_sectors = sectors.sort_values(change_col, ascending=True).head(3)
    cards = st.columns(3)
    for card, (_, row) in zip(cards, top_sectors.iterrows()):
        card.metric(str(row[name_col]), f"{float(row[change_col]):+.2f}%", "强势板块")
    cards2 = st.columns(3)
    for card, (_, row) in zip(cards2, weak_sectors.iterrows()):
        card.metric(str(row[name_col]), f"{float(row[change_col]):+.2f}%", "弱势板块")
    if "成交额" in sectors.columns:
        active_sectors = sectors.sort_values("成交额", ascending=False).head(3)
        active_cards = st.columns(3)
        for card, (_, row) in zip(active_cards, active_sectors.iterrows()):
            card.metric(str(row[name_col]), f"{float(row['成交额']) / 1e8:.2f} 亿", "成交额活跃")
    st.subheader("市场调研总览")
    left, right = st.columns(2)
    with left:
        st.markdown("**强势方向**")
        st.dataframe(sectors.sort_values(change_col, ascending=False).head(8), use_container_width=True, hide_index=True)
    with right:
        st.markdown("**弱势方向**")
        st.dataframe(sectors.sort_values(change_col, ascending=True).head(8), use_container_width=True, hide_index=True)
    if "成交额" in stocks.columns:
        liquid = stocks.sort_values("成交额", ascending=False).head(10)
        st.subheader("市场成交额靠前个股")
        st.dataframe(liquid[[c for c in ("代码", "名称", "涨跌幅", "成交额", "板块") if c in liquid.columns]], use_container_width=True, hide_index=True)
        st.download_button("导出成交额靠前个股 CSV", liquid.to_csv(index=False, encoding="utf-8-sig"), "top_turnover_stocks.csv", "text/csv")
    if "涨跌幅" in stocks.columns:
        movers = stocks.copy()
        movers["涨跌幅"] = pd.to_numeric(movers["涨跌幅"], errors="coerce")
        gainers, losers = movers.sort_values("涨跌幅", ascending=False).head(10), movers.sort_values("涨跌幅", ascending=True).head(10)
        gcol, lcol = st.columns(2)
        with gcol:
            st.subheader("个股涨幅榜")
            st.dataframe(gainers[[c for c in ("代码", "名称", "涨跌幅", "板块") if c in gainers.columns]], use_container_width=True, hide_index=True)
        with lcol:
            st.subheader("个股跌幅榜")
            st.dataframe(losers[[c for c in ("代码", "名称", "涨跌幅", "板块") if c in losers.columns]], use_container_width=True, hide_index=True)
    st.subheader("市场涨跌结构")
    change_values = pd.to_numeric(stocks.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
    if not change_values.empty:
        limit_up = int((change_values >= 9.8).sum())
        limit_down = int((change_values <= -9.8).sum())
        extreme = st.columns(3)
        extreme[0].metric("涨停附近", limit_up)
        extreme[1].metric("跌停附近", limit_down)
        extreme[2].metric("极端波动合计", limit_up + limit_down)
        buckets = pd.cut(change_values, bins=[-100, -5, -2, 0, 2, 5, 100], labels=["跌幅 >5%", "跌 2–5%", "下跌 0–2%", "上涨 0–2%", "涨 2–5%", "涨幅 >5%"])
        structure = buckets.value_counts().reindex(["跌幅 >5%", "跌 2–5%", "下跌 0–2%", "上涨 0–2%", "涨 2–5%", "涨幅 >5%"], fill_value=0)
        breadth_col, structure_col = st.columns(2)
        with breadth_col:
            st.plotly_chart(px.pie(pd.DataFrame({"方向": ["上涨", "下跌", "平盘"], "数量": [up, down, len(change_values) - up - down]}), names="方向", values="数量", hole=0.5), use_container_width=True)
        with structure_col:
            st.bar_chart(structure)
        st.subheader("市场强弱统计")
        total = max(len(change_values), 1)
        breadth_score = max(0, min(100, int(50 + (up - down) / total * 50)))
        stat_cols = st.columns(5)
        stat_cols[0].metric("上涨家数", f"{up:,}")
        stat_cols[1].metric("下跌家数", f"{down:,}")
        stat_cols[2].metric("平盘家数", f"{len(change_values) - up - down:,}")
        stat_cols[3].metric("涨停附近", f"{limit_up:,}")
        stat_cols[4].metric("市场强度", f"{breadth_score}/100")
    if {"板块", "成交额"}.issubset(sectors.columns):
        sector_amount = sectors.copy()
        sector_amount["成交额"] = pd.to_numeric(sector_amount["成交额"], errors="coerce").fillna(0)
        st.subheader("板块成交额排行")
        st.bar_chart(sector_amount.sort_values("成交额", ascending=False).head(15).set_index("板块")["成交额"])
        active_amount = float(sector_amount["成交额"].sum())
        st.caption(f"行业快照成交额合计：{active_amount / 1e8:.2f} 亿元；排行用于观察资金活跃方向，不代表资金流向结论。")
    if not change_values.empty:
        breadth_text = "上涨占优" if up > down * 1.5 else "下跌占优" if down > up * 1.5 else "涨跌分化"
        strongest = str(sectors.sort_values("涨跌幅", ascending=False).iloc[0]["板块"]) if "板块" in sectors.columns else "暂无"
        weakest = str(sectors.sort_values("涨跌幅", ascending=True).iloc[0]["板块"]) if "板块" in sectors.columns else "暂无"
        st.subheader("市场客观摘要")
        st.info(f"当前市场呈现{breadth_text}，有效样本中上涨 {up} 家、下跌 {down} 家，涨跌幅中位数 {change_values.median():+.2f}%。当日最强板块为“{strongest}”，最弱板块为“{weakest}”。以上为导入快照的统计描述，不构成趋势预测或交易建议。")
        snapshot_payload = {"average_change": float(avg), "up": up, "down": down, "strongest_sector": strongest, "weakest_sector": weakest}
        if st.button("保存当前市场快照", key="save_market_snapshot"):
            save_market_snapshot(DB_PATH, datetime.now().date().isoformat(), snapshot_payload)
            st.success("市场快照已保存，可用于后续趋势回看。")
        history_limit = st.slider("历史快照数量", 5, 60, 20, 5, key="market_history_limit")
        history = list_market_snapshots(DB_PATH, limit=int(history_limit))
        if history:
            history_df = pd.DataFrame(history)
            if {"trade_date", "average_change"}.issubset(history_df.columns):
                st.subheader("市场快照趋势")
                history_df["average_change"] = pd.to_numeric(history_df["average_change"], errors="coerce")
                date_options = sorted(history_df["trade_date"].astype(str).unique().tolist(), reverse=True)
                selected_dates = st.multiselect("历史日期筛选", date_options, default=date_options[:10], key="market_history_dates")
                history_view = history_df[history_df["trade_date"].astype(str).isin(selected_dates)] if selected_dates else history_df.head(0)
                st.line_chart(history_view.sort_values("trade_date").set_index("trade_date")["average_change"])
                trend_cols = [c for c in ("up", "down") if c in history_view.columns]
                if trend_cols:
                    st.subheader("市场涨跌家数趋势")
                    st.line_chart(history_view.sort_values("trade_date").set_index("trade_date")[trend_cols])
                history_cols = [c for c in ("trade_date", "average_change", "up", "down", "strongest_sector", "weakest_sector", "saved_at") if c in history_df.columns]
                st.dataframe(history_view.sort_values("trade_date", ascending=False)[history_cols], use_container_width=True, hide_index=True)
                st.download_button("导出市场历史快照 CSV", history_view[history_cols].to_csv(index=False, encoding="utf-8-sig"), "market_snapshot_history.csv", "text/csv")
    if {"板块", "成交额", "涨跌幅"}.issubset(sectors.columns):
        sector_panel = sectors.copy()
        sector_panel["成交额"] = pd.to_numeric(sector_panel["成交额"], errors="coerce").fillna(0)
        sector_panel["涨跌幅"] = pd.to_numeric(sector_panel["涨跌幅"], errors="coerce").fillna(0)
        st.subheader("行业强弱与资金活跃度")
        panel_left, panel_right = st.columns([1.35, 1])
        with panel_left:
            rank_df = sector_panel.sort_values("涨跌幅", ascending=False).head(18).sort_values("涨跌幅")
            rank_fig = px.bar(rank_df, x="涨跌幅", y="板块", orientation="h", color="涨跌幅", color_continuous_scale="RdYlGn", color_continuous_midpoint=0, hover_data=["成交额"])
            rank_fig.update_layout(height=470, margin=dict(t=10, l=0, r=0, b=0), coloraxis_showscale=False)
            st.plotly_chart(rank_fig, use_container_width=True)
        with panel_right:
            active = sector_panel.sort_values("成交额", ascending=False).head(12)
            active_fig = px.scatter(active, x="成交额", y="涨跌幅", size="成交额", color="涨跌幅", text="板块", color_continuous_scale="RdYlGn", color_continuous_midpoint=0)
            active_fig.update_traces(textposition="top center")
            active_fig.update_layout(height=470, margin=dict(t=10, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="成交额", yaxis_title="涨跌幅（%）")
            st.plotly_chart(active_fig, use_container_width=True)
    st.subheader("\u6838\u5fc3\u6307\u6570")
    st.dataframe(indices, use_container_width=True, hide_index=True)
    st.download_button("导出市场指数快照 CSV", indices.to_csv(index=False, encoding="utf-8-sig"), "market_indices.csv", "text/csv")
    st.caption(f"当前展示 {len(indices):,} 个指数，数据来自最近一次导入或演示快照。")
    st.download_button("导出全市场研究快照 CSV", stocks.to_csv(index=False, encoding="utf-8-sig"), "market_research_snapshot.csv", "text/csv")
    if {"名称", "涨跌幅"}.issubset(indices.columns):
        index_snapshot = indices.copy()
        index_snapshot["涨跌幅"] = pd.to_numeric(index_snapshot["涨跌幅"], errors="coerce")
        index_snapshot = index_snapshot.dropna(subset=["涨跌幅"])
        if not index_snapshot.empty:
            st.subheader("主要指数涨跌联动")
            index_fig = px.bar(index_snapshot.sort_values("涨跌幅"), x="涨跌幅", y="名称", orientation="h", color="涨跌幅", color_continuous_scale="RdYlGn", color_continuous_midpoint=0, hover_data=[c for c in ("点位", "成交额") if c in index_snapshot.columns])
            index_fig.update_layout(height=max(300, min(560, 24 * len(index_snapshot) + 100)), margin=dict(t=10, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="涨跌幅（%）")
            st.plotly_chart(index_fig, use_container_width=True)
    st.subheader("\u6982\u5ff5\u6da8\u8dcc\u6392\u540d")
    st.dataframe(sectors.sort_values("\u6da8\u8dcc\u5e45", ascending=False).head(10), use_container_width=True, hide_index=True)
    st.download_button("导出概念板块快照 CSV", sectors.to_csv(index=False, encoding="utf-8-sig"), "concept_snapshot.csv", "text/csv")
    st.subheader("\u677f\u5757\u70ed\u529b\u56fe")
    heatmap = px.treemap(sectors, path=["\u677f\u5757"], values="\u6210\u4ea4\u989d", color="\u6da8\u8dcc\u5e45", color_continuous_scale="RdYlGn", color_continuous_midpoint=0)
    st.plotly_chart(heatmap, use_container_width=True)
    st.download_button("导出市场板块快照 CSV", sectors.to_csv(index=False, encoding="utf-8-sig"), "market_sector_snapshot.csv", "text/csv")
    scatter_cols = {"板块", "成交额", "涨跌幅"}
    if scatter_cols.issubset(sectors.columns):
        scatter = sectors.copy()
        scatter["成交额"] = pd.to_numeric(scatter["成交额"], errors="coerce").fillna(0)
        scatter["涨跌幅"] = pd.to_numeric(scatter["涨跌幅"], errors="coerce").fillna(0)
        st.subheader("板块活跃度与强弱")
        st.plotly_chart(px.scatter(scatter, x="成交额", y="涨跌幅", size="成交额", color="涨跌幅", hover_name="板块", color_continuous_scale="RdYlGn", color_continuous_midpoint=0), use_container_width=True)
    if {"板块", "名称", "成交额", "涨跌幅"}.issubset(stocks.columns):
        stock_map = stocks.copy().sort_values("成交额", ascending=False).head(150)
        stock_map["成交额"] = pd.to_numeric(stock_map["成交额"], errors="coerce").fillna(0)
        stock_map["涨跌幅"] = pd.to_numeric(stock_map["涨跌幅"], errors="coerce").fillna(0)
        st.subheader("个股成交热力图（前 150 只）")
        st.plotly_chart(px.treemap(stock_map, path=["板块", "名称"], values="成交额", color="涨跌幅", color_continuous_scale="RdYlGn", color_continuous_midpoint=0), use_container_width=True)


def render_index_analysis(data):
    from .public_workspace.pages.index_analysis import render_frame
    from .public_workspace.contracts import PublicCapabilities
    from .public_workspace.navigation import PublicNavigation
    render_frame(data.get('indices',pd.DataFrame()),PublicCapabilities(download=True),
        PublicNavigation('owner',('指数分析',),st.session_state))


def _owner_sector_navigation(stocks,source):
    """Owner entry bridge only; shared renderers never import this module."""
    from .public_workspace.navigation import PublicNavigation
    class OwnerSectorNavigation(PublicNavigation):
        def open_page(self,page):
            if not super().open_page(page): return False
            self.state["active_nav"]=page
            if page=="大盘云图":
                target=self.state.get("concept_sector")
                if isinstance(target,str) and target:
                    self.state["terminal_industry_query"]=target
                    self.state["terminal_level"]=market_navigation_level(stocks,target,fallback="板块")
                    self.state["research_context"]={"source":source,"industry":target}
            return True
        def focus_sector(self,field,value,allowed_pairs,parent=None):
            if not super().focus_sector(field,value,allowed_pairs,parent): return False
            self.state["terminal_industry_query"]=value
            self.state["terminal_level"]=field
            self.state["research_context"]={"source":source,"industry":value}
            self.state["active_nav"]="大盘云图"
            return True
        def open_stock(self,code,allowed_codes,industry=None,parent=None):
            if not super().open_stock(code,allowed_codes,industry,parent): return False
            self.state["stock_detail_query"]=code
            self.state.pop("stock_detail_selection",None)
            if industry: self.state["research_context"]={"source":source,"industry":industry}
            self.state["active_nav"]="个股详情"
            return True
    return OwnerSectorNavigation("owner",("概念排行","板块热力图","大盘云图","个股详情"),st.session_state)


def render_concept_ranking(data):
    from .public_workspace.pages.concepts import render_frame
    from .public_workspace.contracts import PublicCapabilities
    st.caption(data.get("source_notice") or "既有板块来源展示；未经核验的归属不视为真实概念成分。")
    stocks=data.get("stocks",pd.DataFrame())
    render_frame(data.get("sectors",pd.DataFrame()),stocks,PublicCapabilities(download=True),
        _owner_sector_navigation(stocks,"概念排行"))


def filter_stocks(df, minimum_score=60, sector="全部"):
    out = df[df["综合分"] >= minimum_score]
    return out if sector == "全部" else out[out["板块"] == sector]


def render_stock_detail(data):
    df = data["stocks"].copy()
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if df.empty or "\u4ee3\u7801" not in df.columns:
        st.error("\u5f53\u524d\u6ca1\u6709\u53ef\u7528\u80a1\u7968\u8bb0\u5f55")
        return
    st.title("\U0001f4c4\u4e2a\u80a1\u7814\u7a76\u5361")
    search = st.text_input("\u641c\u7d22\u4ee3\u7801\u6216\u540d\u79f0", placeholder="\u4f8b\uff1a688008\u3001\u6f9c\u8d77\u3001\u4e2d\u9645")
    if search:
        code_values = df["\u4ee3\u7801"].astype(str)
        name_values = df.get("\u540d\u79f0", pd.Series(index=df.index, dtype=str)).astype(str)
        matches = df[code_values.str.contains(search, case=False, na=False) | name_values.str.contains(search, case=False, na=False)]
    else:
        matches = df.head(200)
    if matches.empty:
        st.warning("\u6ca1\u6709\u627e\u5230\u5339\u914d\u7684\u80a1\u7968")
        return
    code = st.selectbox(f"\u9009\u62e9\u80a1\u7968\uff08\u5339\u914d {len(matches)} \u53ea\uff09", matches["\u4ee3\u7801"].astype(str).tolist())
    row = df[df["\u4ee3\u7801"].astype(str) == str(code)].iloc[0]
    def get(field, default="\u2014"):
        raw = row.get(field, default)
        return default if pd.isna(raw) else raw
    def num(field):
        return pd.to_numeric(pd.Series([get(field, None)]), errors="coerce").iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    stock_name = get("\u540d\u79f0")
    latest_price = num("\u4ef7\u683c")
    change_pct = num("\u6da8\u8dcc\u5e45")
    amount = num("\u6210\u4ea4\u989d")
    c1.metric("\u80a1\u7968", f"{code} {stock_name}")
    c2.metric("\u6700\u65b0\u4ef7", f"{latest_price:.2f}" if pd.notna(latest_price) else "\u2014")
    c3.metric("\u6da8\u8dcc\u5e45", f"{change_pct:+.2f}%" if pd.notna(change_pct) else "\u2014")
    c4.metric("\u6210\u4ea4\u989d", f"{amount/1e8:.2f}\u4ebf" if pd.notna(amount) else "\u2014")
    tags = [f"{field}\uff1a{get(field)}" for field in ("\u677f\u5757", "\u884c\u4e1a", "\u7ec6\u5206\u884c\u4e1a", "\u6807\u7b7e") if field in df.columns and str(get(field)) not in {"", "\u2014", "nan"}]
    st.subheader("\u7814\u7a76\u6807\u7b7e")
    st.info(" \u00b7 ".join(tags) if tags else "\u5f53\u524d\u5feb\u7167\u672a\u63d0\u4f9b\u884c\u4e1a\u6216\u9898\u6750\u6807\u7b7e\u3002")
    fields = ["\u7efc\u5408\u5206", "\u98ce\u9669\u5206", "\u6362\u624b\u7387", "\u91cf\u6bd4", "\u6210\u4ea4\u91cf"]
    details = {field: get(field) for field in fields if field in df.columns}
    if details:
        st.subheader("\u8f85\u52a9\u6570\u636e")
        st.dataframe(pd.DataFrame([details]), use_container_width=True, hide_index=True)
    related_cols = [c for c in ("板块", "行业", "细分行业", "标签") if c in df.columns]
    if related_cols:
        related_mask = pd.Series(False, index=df.index)
        for field in related_cols:
            value = str(get(field, ""))
            if value and value != "—":
                related_mask |= df[field].fillna("").astype(str).str.contains(value, regex=False)
        related = df[related_mask & (df["代码"].astype(str) != str(code))].head(10)
        if not related.empty:
            st.subheader("同题材 / 同行业参考")
            st.dataframe(related[[c for c in ("代码", "名称", "价格", "涨跌幅", "成交额", "板块", "行业") if c in related.columns]], use_container_width=True, hide_index=True)
    st.caption("\u6570\u636e\u6765\u81ea\u6700\u8fd1\u4e00\u6b21\u5bfc\u5165\u5feb\u7167\uff0c\u4ec5\u7528\u4e8e\u7814\u7a76\u548c\u590d\u76d8\uff0c\u4e0d\u662f\u5b9e\u65f6\u884c\u60c5\u6216\u4e70\u5356\u4fe1\u53f7\u3002")


def render_intraday_scanner(data):
    st.title("盘中选股")
    df = data["stocks"]
    sectors = ["全部", *sorted(df["板块"].unique())]
    sector = st.selectbox("板块", sectors)
    score = st.slider("最低综合分", 0, 100, 60)
    result = filter_stocks(df, score, sector)
    st.info(f"当前展示 {len(result)} 只候选股，仅作为研究观察名单。")
    st.dataframe(result, use_container_width=True, hide_index=True)
    if not result.empty and "涨跌幅" in result.columns:
        chart = result.head(20).copy()
        chart["涨跌幅"] = pd.to_numeric(chart["涨跌幅"], errors="coerce")
        if "名称" in chart.columns:
            st.subheader("候选涨跌幅排行")
            st.bar_chart(chart.set_index("名称")["涨跌幅"])
    if not result.empty and "板块" in result.columns:
        st.subheader("候选板块分布")
        st.bar_chart(result["板块"].fillna("未分类").astype(str).value_counts().head(12))


def render_sector_heatmap(data):
    from .public_workspace.pages.heatmap import render_frame
    from .public_workspace.contracts import PublicCapabilities
    stocks=data.get("stocks",pd.DataFrame())
    render_frame(dict(stocks=stocks,sectors=data.get("sectors",pd.DataFrame())),PublicCapabilities(download=True),
        _owner_sector_navigation(stocks,"板块热力图"))


def render_industry_chain(data):
    st.title("产业链分层")
    groups = {"上游材料":["能源金属"], "核心制造":["PCB","半导体/存储"], "算力与应用":["算力/IT服务","AI服务器/消费电子"]}
    for name, sectors in groups.items():
        st.subheader(name)
        st.dataframe(data["stocks"][data["stocks"]["板块"].isin(sectors)], use_container_width=True, hide_index=True)


def render_stock_detail(data):
    st.title("个股详情")
    df = data["stocks"]
    code = st.selectbox("选择股票", df["代码"])
    row = df[df["代码"] == code].iloc[0]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("最新价", f"{row['价格']:.2f}")
    c2.metric("涨跌幅", f"{row['涨跌幅']:+.2f}%")
    c3.metric("综合分", int(row["综合分"]))
    c4.metric("风险分", int(row["风险分"]))
    st.write(f"标签：{row['标签']}　|　板块：{row['板块']}")
    st.warning("此页面展示研究信息，不构成买卖建议。")


def render_intraday_scanner(data):
    from .pages_scanner import render_candidate_workspace
    render_candidate_workspace(data)


def render_industry_chain(data):
    st.title("\u4ea7\u4e1a\u94fe\u5206\u5c42")
    df = data["stocks"].copy()
    industry_cols = [c for c in ("\u7ec6\u5206\u884c\u4e1a", "\u884c\u4e1a", "\u6807\u7b7e") if c in df.columns]
    if not industry_cols:
        st.info("\u5f53\u524d\u6570\u636e\u6ca1\u6709\u884c\u4e1a\u5206\u7c7b\u5b57\u6bb5\uff0c\u5bfc\u5165\u5305\u542b\u884c\u4e1a\u5217\u7684\u540c\u82b1\u987a\u6570\u636e\u540e\u53ef\u5c55\u793a\u4ea7\u4e1a\u94fe\u6807\u7684")
        return
    groups = {
        "\u534a\u5bfc\u4f53 / \u5b58\u50a8": ("\u534a\u5bfc\u4f53", "\u5b58\u50a8", "\u82af\u7247", "\u96c6\u6210\u7535\u8def"),
        "\u7b97\u529b / \u5149\u901a\u4fe1 / PCB": ("\u7b97\u529b", "\u5149\u901a\u4fe1", "\u901a\u4fe1", "CPO", "PCB", "\u670d\u52a1\u5668"),
        "\u673a\u5668\u4eba / \u81ea\u52a8\u5316": ("\u673a\u5668\u4eba", "\u81ea\u52a8\u5316", "\u5de5\u4e1a\u63a7\u5236"),
        "\u6709\u8272 / \u80fd\u6e90\u91d1\u5c5e": ("\u6709\u8272", "\u80fd\u6e90\u91d1\u5c5e", "\u9502", "\u94dc", "\u91d1\u5c5e"),
    }
    chain_overview = industry_chain_summary(df, groups, industry_cols)
    st.subheader("产业链研究总览", icon=":material/account_tree:")
    st.caption("按行业、细分行业和标签关键词匹配形成研究链条。个股可匹配多条链，因此链条样本数不相加为全市场总数。")
    if not chain_overview.empty:
        chain_overview["平均涨跌"] = pd.to_numeric(chain_overview["平均涨跌"], errors="coerce")
        chain_overview["上涨占比"] = pd.to_numeric(chain_overview["上涨占比"], errors="coerce")
        chain_overview["成交额"] = pd.to_numeric(chain_overview["成交额"], errors="coerce").fillna(0.0)
        strongest = chain_overview.dropna(subset=["平均涨跌"]).sort_values("平均涨跌", ascending=False)
        with st.container(horizontal=True):
            st.metric("研究链条", len(chain_overview), border=True)
            st.metric("最强链条", strongest.iloc[0]["产业链"] if not strongest.empty else "—", border=True)
            st.metric("最高平均涨跌", f"{strongest.iloc[0]['平均涨跌']:+.2f}%" if not strongest.empty else "—", border=True)
            st.metric("匹配成交额", f"{chain_overview['成交额'].sum() / 1e8:.2f} 亿", border=True)
        chain_left, chain_right = st.columns([1.15, 1], vertical_alignment="top")
        with chain_left:
            chain_chart = px.bar(
                chain_overview.dropna(subset=["平均涨跌"]).sort_values("平均涨跌"),
                x="平均涨跌", y="产业链", orientation="h", color="平均涨跌",
                color_continuous_scale="RdYlGn_r", color_continuous_midpoint=0,
                hover_data={"股票数": True, "上涨占比": ":.0%", "成交额": ":.3s"},
            )
            chain_chart.update_layout(height=300, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="平均涨跌幅（%）", yaxis_title="")
            st.plotly_chart(chain_chart, width="stretch")
        with chain_right:
            st.dataframe(
                _ashare_change_style(chain_overview),
                column_config={
                    "股票数": st.column_config.NumberColumn("样本数", format="%,d"),
                    "平均涨跌": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
                    "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
                    "成交额": st.column_config.NumberColumn("成交额", format="compact"),
                },
                width="stretch", hide_index=True, height=300,
            )
    for title, terms in groups.items():
        mask = pd.Series(False, index=df.index)
        for col in industry_cols:
            values = df[col].fillna("").astype(str)
            for term in terms:
                mask |= values.str.contains(term, case=False, regex=False)
        st.subheader(title)
        selected_chain = df[mask].copy()
        chain_change = pd.to_numeric(selected_chain.get("涨跌幅", pd.Series(index=selected_chain.index)), errors="coerce").dropna()
        chain_cols = st.columns(3)
        chain_cols[0].metric("覆盖股票", len(selected_chain))
        chain_cols[1].metric("上涨占比", f"{(chain_change > 0).mean() * 100:.1f}%" if not chain_change.empty else "暂无")
        chain_cols[2].metric("平均涨跌", f"{chain_change.mean():+.2f}%" if not chain_change.empty else "暂无")
        st.dataframe(selected_chain.head(100), use_container_width=True, hide_index=True)
        if not selected_chain.empty and "涨跌幅" in selected_chain.columns:
            selected_chain["涨跌幅"] = pd.to_numeric(selected_chain["涨跌幅"], errors="coerce")
            winners = selected_chain.nlargest(10, "涨跌幅")
            if "名称" in winners.columns:
                st.plotly_chart(px.bar(winners.sort_values("涨跌幅"), x="涨跌幅", y="名称", orientation="h", color="涨跌幅", color_continuous_scale="RdYlGn", color_continuous_midpoint=0), use_container_width=True)
    st.caption("产业链匹配来自导入文件的行业、细分行业或标签字段；同一只股票可能属于多个研究方向。")


def render_theme_compare(data):
    st.title("主题比较")
    st.caption("适合把同一题材的 3–6 只股票放在一起比较；只做研究整理，不自动下单。")
    df = data.get("stocks", pd.DataFrame()).copy()
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if "代码" not in df.columns:
        st.warning("当前导入数据缺少代码列，请重新导入同花顺全市场数据。")
        return
    df["代码"] = df["代码"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    name_col = "名称" if "名称" in df.columns else None
    theme_terms = {
        "全部股票": (),
        "CPO / 光通信 / PCB": ("CPO", "光通信", "光模块", "PCB", "通信"),
        "存储半导体": ("存储", "存储器", "半导体", "芯片", "集成电路"),
        "机器人 / 自动化": ("机器人", "自动化", "工业控制", "减速器"),
        "国产替代": ("国产替代", "自主可控", "信创", "服务器", "半导体"),
        "消费电子": ("消费电子", "电子", "苹果产业链", "手机", "面板"),
    }
    theme = st.selectbox("快速主题筛选", list(theme_terms))
    if theme != "全部股票":
        text_cols = [c for c in ("板块", "行业", "细分行业", "标签", "名称") if c in df.columns]
        if text_cols:
            combined = df[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
            mask = pd.Series(False, index=df.index)
            for term in theme_terms[theme]:
                mask |= combined.str.contains(term, case=False, regex=False)
            df = df[mask].copy()
        else:
            st.caption("当前数据没有板块/行业字段，主题筛选暂不可用。")
    search = st.text_input("搜索股票", placeholder="输入代码或名称，例如：中际、688498")
    candidates = df
    if search.strip():
        mask = df["代码"].str.contains(search.strip(), case=False, regex=False)
        if name_col:
            mask |= df[name_col].fillna("").astype(str).str.contains(search.strip(), case=False, regex=False)
        candidates = df[mask]
    if candidates.empty:
        st.warning("当前筛选条件没有匹配股票，请更换主题或搜索关键词。")
        return
    labels = []
    label_to_code = {}
    for _, row in candidates.head(300).iterrows():
        label = f"{row['代码']} {row[name_col]}" if name_col else str(row["代码"])
        labels.append(label)
        label_to_code[label] = row["代码"]
    if not labels:
        st.warning("当前数据没有可用于比较的股票。")
        return
    selected_labels = st.multiselect("选择比较对象（最多 6 只）", labels, max_selections=6)
    if not selected_labels:
        st.info("先搜索并选择 3–6 只股票；也可以直接输入代码搜索。")
        return
    selected = compare_stock_pool(df, [label_to_code[x] for x in selected_labels], limit=6)
    preferred = ["代码", "名称", "价格", "涨跌幅", "成交额", "换手率", "行业", "细分行业", "板块", "标签"]
    display_cols = [c for c in preferred if c in selected.columns]
    st.subheader(f"比较结果（{len(selected)} 只）")
    sort_col = st.selectbox("排序依据", [c for c in ("涨跌幅", "成交额", "换手率", "价格") if c in selected.columns] or ["代码"])
    if sort_col != "代码":
        selected = selected.assign(_sort=pd.to_numeric(selected[sort_col], errors="coerce")).sort_values("_sort", ascending=False).drop(columns=["_sort"])
    metric_cols = st.columns(3)
    change_values = pd.to_numeric(selected.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
    turnover_values = pd.to_numeric(selected.get("换手率", pd.Series(dtype=float)), errors="coerce").dropna()
    metric_cols[0].metric("比较数量", f"{len(selected)} 只")
    metric_cols[1].metric("平均涨跌幅", f"{change_values.mean():+.2f}%" if not change_values.empty else "暂无")
    metric_cols[2].metric("平均换手率", f"{turnover_values.mean():.2f}%" if not turnover_values.empty else "暂无")
    if "成交额" in selected.columns:
        amount_values = pd.to_numeric(selected["成交额"], errors="coerce").dropna()
        st.caption(f"本组成交额合计：{amount_values.sum() / 1e8:.2f} 亿元；上涨股票：{int((change_values > 0).sum())} 只。")
    if not change_values.empty:
        strongest_name = str(selected.loc[change_values.idxmax(), name_col]) if name_col and change_values.idxmax() in selected.index else "—"
        weakest_name = str(selected.loc[change_values.idxmin(), name_col]) if name_col and change_values.idxmin() in selected.index else "—"
        st.info(f"本组最强：{strongest_name}；最弱：{weakest_name}。以上为当前快照横向比较，不代表后续收益。")
    st.dataframe(selected[display_cols], use_container_width=True, hide_index=True)
    numeric_chart = selected.copy()
    if "涨跌幅" in numeric_chart.columns:
        numeric_chart["涨跌幅"] = pd.to_numeric(numeric_chart["涨跌幅"], errors="coerce")
        chart_name = name_col if name_col else "代码"
        chart_data = numeric_chart[[chart_name, "涨跌幅"]].dropna().set_index(chart_name)
    if not chart_data.empty:
            st.subheader("比较图：当日涨跌幅")
            compare_fig = px.bar(chart_data.reset_index(), x="涨跌幅", y=chart_name, orientation="h", color="涨跌幅", color_continuous_scale="RdYlGn", color_continuous_midpoint=0)
            compare_fig.update_layout(height=360, margin=dict(t=10, l=0, r=0, b=0), coloraxis_showscale=False)
            st.plotly_chart(compare_fig, use_container_width=True)
            if "成交额" in numeric_chart.columns:
                amount_frame = numeric_chart[[chart_name, "成交额"]].copy()
                amount_frame["成交额"] = pd.to_numeric(amount_frame["成交额"], errors="coerce")
                amount_frame = amount_frame.dropna().sort_values("成交额", ascending=False)
                if not amount_frame.empty:
                    st.subheader("比较图：成交额")
                    st.bar_chart(amount_frame.head(6).set_index(chart_name)["成交额"])
    research_note = st.text_area("本组研究备注", placeholder="记录题材逻辑、龙头/补涨关系、跟踪触发条件和失效条件……")
    export_frame = selected[display_cols].copy()
    export_frame.insert(0, "比较主题", theme)
    export_frame.insert(1, "导出时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    export_frame["研究备注"] = research_note
    if st.button("保存本次主题快照"):
        changes = pd.to_numeric(selected.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
        save_theme_snapshot(DB_PATH, datetime.now().date().isoformat(), theme, {
            "count": int(len(selected)),
            "average_change": float(changes.mean()) if not changes.empty else None,
            "codes": selected["代码"].astype(str).tolist(),
        })
        st.success("主题快照已保存。")
    history = list_theme_snapshots(DB_PATH, limit=10)
    if history:
        st.caption("最近主题快照")
        history_df = pd.DataFrame(history)[["trade_date", "theme", "count", "average_change"]]
        st.dataframe(history_df, use_container_width=True, hide_index=True)
        st.download_button("导出主题历史快照 CSV", history_df.to_csv(index=False, encoding="utf-8-sig"), "theme_snapshot_history.csv", "text/csv")
        trend = history_df.dropna(subset=["average_change"]).copy()
        if not trend.empty:
            trend["average_change"] = pd.to_numeric(trend["average_change"], errors="coerce")
            st.line_chart(trend.pivot_table(index="trade_date", columns="theme", values="average_change", aggfunc="mean"))
            latest = trend.sort_values("trade_date").groupby("theme").tail(1).sort_values("average_change", ascending=False)
            st.caption("最近一次主题表现：" + "；".join(f"{row['theme']} {row['average_change']:+.2f}%" for _, row in latest.iterrows()))
    st.download_button("导出主题比较 CSV", export_frame.to_csv(index=False, encoding="utf-8-sig"), "theme_comparison.csv", "text/csv")


def render_industry_chain(data):
    st.title("\u4ea7\u4e1a\u94fe\u5206\u5c42")
    df = data["stocks"].copy()
    df = df.loc[:, ~df.columns.duplicated()].copy()
    industry_cols = [c for c in ("\u7ec6\u5206\u884c\u4e1a", "\u884c\u4e1a", "\u6807\u7b7e") if c in df.columns]
    if not industry_cols:
        st.info("\u5f53\u524d\u5bfc\u5165\u5feb\u7167\u6ca1\u6709\u884c\u4e1a\u5206\u7c7b\u5b57\u6bb5")
        return
    groups = {
        "\u534a\u5bfc\u4f53 / \u5b58\u50a8": ("\u534a\u5bfc\u4f53", "\u5b58\u50a8", "\u82af\u7247", "\u96c6\u6210\u7535\u8def"),
        "\u7b97\u529b / \u5149\u901a\u4fe1 / PCB": ("\u7b97\u529b", "\u5149\u901a\u4fe1", "\u901a\u4fe1", "CPO", "PCB", "\u670d\u52a1\u5668"),
        "\u673a\u5668\u4eba / \u81ea\u52a8\u5316": ("\u673a\u5668\u4eba", "\u81ea\u52a8\u5316", "\u5de5\u4e1a\u63a7\u5236"),
        "\u6709\u8272 / \u80fd\u6e90\u91d1\u5c5e": ("\u6709\u8272", "\u80fd\u6e90\u91d1\u5c5e", "\u9502", "\u94dc", "\u91d1\u5c5e"),
    }
    chain_overview = industry_chain_summary(df, groups, industry_cols)
    st.subheader("产业链研究总览", icon=":material/account_tree:")
    st.caption("按行业、细分行业和标签关键词匹配形成研究链条。个股可匹配多条链，因此链条样本数不相加为全市场总数。")
    if not chain_overview.empty:
        chain_overview["平均涨跌"] = pd.to_numeric(chain_overview["平均涨跌"], errors="coerce")
        chain_overview["上涨占比"] = pd.to_numeric(chain_overview["上涨占比"], errors="coerce")
        chain_overview["成交额"] = pd.to_numeric(chain_overview["成交额"], errors="coerce").fillna(0.0)
        strongest = chain_overview.dropna(subset=["平均涨跌"]).sort_values("平均涨跌", ascending=False)
        with st.container(horizontal=True):
            st.metric("研究链条", len(chain_overview), border=True)
            st.metric("最强链条", strongest.iloc[0]["产业链"] if not strongest.empty else "—", border=True)
            st.metric("最高平均涨跌", f"{strongest.iloc[0]['平均涨跌']:+.2f}%" if not strongest.empty else "—", border=True)
            st.metric("匹配成交额", f"{chain_overview['成交额'].sum() / 1e8:.2f} 亿", border=True)
        chain_left, chain_right = st.columns([1.15, 1], vertical_alignment="top")
        with chain_left:
            chain_chart = px.bar(chain_overview.dropna(subset=["平均涨跌"]).sort_values("平均涨跌"), x="平均涨跌", y="产业链", orientation="h", color="平均涨跌", color_continuous_scale="RdYlGn_r", color_continuous_midpoint=0, hover_data={"股票数": True, "上涨占比": ":.0%", "成交额": ":.3s"})
            chain_chart.update_layout(height=300, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="平均涨跌幅（%）", yaxis_title="")
            st.plotly_chart(chain_chart, width="stretch")
        with chain_right:
            st.dataframe(_ashare_change_style(chain_overview), column_config={"股票数": st.column_config.NumberColumn("样本数", format="%,d"), "平均涨跌": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"), "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"), "成交额": st.column_config.NumberColumn("成交额", format="compact")}, width="stretch", hide_index=True, height=300)
    summary = []
    for title, terms in groups.items():
        mask = pd.Series(False, index=df.index)
        for col in industry_cols:
            values = df[col].fillna("").astype(str)
            for term in terms:
                mask |= values.str.contains(term, case=False, regex=False)
        selected = df[mask].copy()
        changes = pd.to_numeric(selected.get("\u6da8\u8dcc\u5e45", pd.Series(index=selected.index)), errors="coerce").dropna()
        summary.append({
            "\u4ea7\u4e1a\u94fe": title,
            "\u80a1\u7968\u6570": len(selected),
            "\u5e73\u5747\u6da8\u8dcc": f"{changes.mean():+.2f}%" if not changes.empty else "\u65e0\u6570\u636e",
            "\u4e0a\u6da8\u5360\u6bd4": f"{(changes > 0).mean():.1%}" if not changes.empty else "\u65e0\u6570\u636e",
        })
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.download_button("导出产业链强弱摘要 CSV", pd.DataFrame(summary).to_csv(index=False, encoding="utf-8-sig"), "industry_chain_summary.csv", "text/csv")
    summary_chart = pd.DataFrame(summary).copy()
    summary_chart["平均涨跌数值"] = pd.to_numeric(summary_chart["平均涨跌"].str.replace("%", "", regex=False), errors="coerce")
    if summary_chart["平均涨跌数值"].notna().any():
        st.subheader("产业链强弱对比")
        st.bar_chart(summary_chart.set_index("产业链")["平均涨跌数值"])
    st.caption("\u5206\u5c42\u5339\u914d\u6765\u81ea\u5bfc\u5165\u6587\u4ef6\u7684\u884c\u4e1a\u3001\u7ec6\u5206\u884c\u4e1a\u6216\u6807\u7b7e\u5b57\u6bb5\uff1b\u4e00\u53ea\u80a1\u53ef\u80fd\u540c\u65f6\u5339\u914d\u591a\u4e2a\u5173\u952e\u8bcd\u3002")
    for title, terms in groups.items():
        mask = pd.Series(False, index=df.index)
        for col in industry_cols:
            values = df[col].fillna("").astype(str)
            for term in terms:
                mask |= values.str.contains(term, case=False, regex=False)
        st.subheader(title)
        st.dataframe(df[mask].head(100), use_container_width=True, hide_index=True)
        st.download_button(f"导出{title}成分股 CSV", df[mask].to_csv(index=False, encoding="utf-8-sig"), f"{title.replace(' ', '_')}.csv", "text/csv", key=f"export_chain_{title}")


def _render_combined_industry_chain(data):
    from .public_workspace.pages.industry_chain import render_combined
    from .public_workspace.contracts import PublicCapabilities
    render_combined(data.get('stocks',pd.DataFrame()),PublicCapabilities(download=True))


def render_industry_chain(data):
    from .public_workspace.pages.industry_chain import render_frame
    from .public_workspace.contracts import PublicCapabilities
    from .reference_chain import owner_chain_navigation
    render_frame(data.get('stocks',pd.DataFrame()),data.get('import_date'),
        PublicCapabilities(download=True),owner_chain_navigation())


def _owner_render_stock_daily(selected_code):
    st.subheader('个股 K 线', icon=':material/candlestick_chart:')
    st.caption('自动获取单只股票最近三年日线；首次加载后保存在本地缓存，每个自然日自动更新一次。周 K、月 K 由日线聚合；当前周期未结束时显示进行中的 K 线。行情为收盘后日线，不是盘中实时行情。')
    range_col, period_col, adjustment_col, refresh_col = st.columns([1.8, 1.15, 1.4, 0.8], vertical_alignment='bottom')
    with range_col:
        display_range = st.segmented_control(
            '显示区间', ['3个月', '6个月', '1年', '3年'], default='1年',
            key=f'stock_daily_range_{selected_code}',
        ) or '1年'
    with period_col:
        kline_period = st.segmented_control(
            'K线周期', ['日K', '周K', '月K'], default='日K',
            key=f'stock_kline_period_{selected_code}',
        ) or '日K'
    with adjustment_col:
        adjustment = st.segmented_control(
            '复权方式', ['前复权', '不复权'], default='前复权',
            key=f'stock_daily_adjustment_{selected_code}',
        ) or '前复权'
    with refresh_col:
        force_daily_refresh = st.button(
            '刷新日线', icon=':material/refresh:', key=f'stock_daily_refresh_{selected_code}',
            help='跳过今日缓存，立即从公开行情源重新获取。',
        )
    with st.spinner('正在读取本地日线缓存或更新行情数据…'):
        from .stock_history import load_stock_daily_history
        daily_bars, daily_metadata, daily_error = load_stock_daily_history(
            selected_code, adjustment=adjustment, force_refresh=force_daily_refresh,
        )
    if daily_bars.empty:
        st.warning('暂时无法自动获取日线。请稍后刷新；如果公开行情源不可用，可配置 Tushare 日线服务后再接入。')
        if daily_error:
            st.caption(f'数据源提示：{daily_error}')
    else:
        from .public_workspace.pages.daily import render_chart
        from .public_workspace.contracts import PublicCapabilities

        render_chart(daily_bars, daily_metadata, daily_error, selected_code,
                     adjustment, kline_period, display_range,
                     PublicCapabilities(download=True))


def render_stock_detail(data):
    from .public_workspace.pages.stock_detail import render_frame
    from .public_workspace.contracts import PublicCapabilities
    from .public_workspace.navigation import PublicNavigation

    class OwnerDetailNavigation(PublicNavigation):
        def open_page(self,page):
            if not super().open_page(page): return False
            self.state["active_nav"]=page
            return True
        def open_stock(self,code,allowed_codes,industry=None,parent=None):
            if not super().open_stock(code,allowed_codes,industry,parent): return False
            self.state["active_nav"]="个股详情"
            return True
        def focus_sector(self,field,value,allowed_pairs,parent=None):
            if not super().focus_sector(field,value,allowed_pairs,parent): return False
            from .sector_lens import open_sector_cloud
            open_sector_cloud(field,value,parent if field=='细分行业' else None)
            return True
    navigation=OwnerDetailNavigation("owner",("市场总览","大盘云图","个股详情"),st.session_state)
    return render_frame(data,PublicCapabilities(download=True),navigation,
                        daily_renderer=_owner_render_stock_daily)



def render_market_overview(data):
    from .public_workspace.pages.overview import render_frame
    from .public_workspace.contracts import PublicCapabilities
    from .core_workspace import owner_cloud_navigation
    from .market_temperature import render_market_temperature
    from .closing_report import owner_overview_panels
    prepared=owner_overview_panels(data).data
    return render_frame(prepared,PublicCapabilities(download=True),owner_cloud_navigation(),
                        owner_temperature_ui=render_market_temperature)


def _select_detail_neighbor(label):
    st.session_state["stock_detail_selection"] = label


def rank_peer_quotes(peers, sort_field, ascending=False):
    from .public_workspace.detail_model import rank_peer_quotes as shared
    return shared(peers,sort_field,ascending)


def _open_peer_stock(code):
    st.session_state["stock_detail_query"] = str(code)
    st.session_state.pop("stock_detail_selection", None)
    st.session_state["active_nav"] = "个股详情"


def _focus_cloud_group(group):
    if group == "全市场":
        _clear_terminal_industry_context()
    else:
        _set_terminal_research_context(group)


def _reset_terminal_preset_controls():
    for key in ("terminal_size", "terminal_level", "terminal_color", "terminal_minimum"):
        st.session_state.pop(key, None)


def render_market_terminal(data):
    from .public_workspace.pages.cloud import render_frame
    from .public_workspace.contracts import PublicCapabilities
    from .core_workspace import owner_cloud_navigation
    return render_frame(data,PublicCapabilities(download=True),owner_cloud_navigation())


def _follow_latest_replay_date(state_key, dates):
    """Select a new trading day once, while preserving deliberate history browsing."""
    from .public_workspace.capital_model import follow_latest_replay_date
    return follow_latest_replay_date(st.session_state,state_key,dates)


def render_capital_replay(data):
    """Live sampling and historical replay of industry capital-flow snapshots."""
    from .capital_flow_source import CAPITAL_FLOW_SECTORS

    stocks = data.get("stocks", pd.DataFrame()).copy()
    replay_dir = data.get("capital_replay_dir", "data/capital_replay")
    replay = load_capital_replay(replay_dir)
    st.title("板块资金流向", icon=":material/timeline:")
    _render_research_context("capital_replay")
    latest_capture = replay["时间"].dropna().astype(str).max() if not replay.empty else "暂无"
    st.caption(f"数据源：东方财富行业及概念资金流；该源失败时尝试同花顺公开排行。切换资金源后，回放按来源分段，不跨口径连线。后台定时任务在A股交易时段每5分钟尝试采集，页面无需保持打开；本机须开机联网。最新板块资金快照：{latest_capture}。")
    capture_status_path = Path(replay_dir) / "capture_status.json"
    if capture_status_path.exists():
        try:
            background_status = json.loads(capture_status_path.read_text(encoding="utf-8"))
            if background_status.get("status") == "failed":
                st.warning(f"后台采集连续失败 {background_status.get('consecutive_failures', 1)} 次；上次成功的回放仍保留。")
        except (OSError, ValueError, TypeError):
            st.caption("后台采集状态暂不可读，回放仍以已保存快照为准。")
    with st.container(horizontal=True):
        if st.button("返回市场总览", icon=":material/dashboard:", key="replay_to_overview"):
            st.session_state["active_nav"] = "市场总览"
            st.rerun()
        if st.button("查看大盘云图", icon=":material/account_tree:", key="replay_to_terminal"):
            st.session_state["active_nav"] = "大盘云图"
            st.rerun()
        capture_now = _china_market_session(datetime.now())
        button_label = "现在采集一次" if capture_now else "检测资金源连接"
        if st.button(button_label, icon=":material/refresh:", key="capital_flow_manual_capture"):
            with st.spinner("正在获取行业和概念资金排行…"):
                collected, path, error = _collect_capital_flow_snapshot(replay_dir, persist=capture_now)
            if error:
                action = "采集" if capture_now else "连接检测"
                st.session_state["capital_flow_capture_status"] = f"{action}失败｜{error}"
            else:
                if capture_now:
                    st.session_state["capital_flow_capture_status"] = f"采集成功｜{collected['时间'].iloc[0]}｜{len(collected)} / {len(CAPITAL_FLOW_SECTORS)} 个指定板块"
                    st.session_state["capital_flow_captured_bucket"] = _capital_flow_capture_bucket(datetime.now())
                else:
                    st.session_state["capital_flow_capture_status"] = f"连接检测成功｜{len(collected)} / {len(CAPITAL_FLOW_SECTORS)} 个指定板块可用｜盘后未写入回放"
            st.rerun()
    status = st.session_state.get("capital_flow_capture_status")
    if status:
        if "失败" in status:
            st.warning(f"{status}。已有快照继续保留。", icon=":material/warning:")
        else:
            st.success(status, icon=":material/check_circle:")
    if st.session_state.get("capital_flow_source_switch"):
        st.info(st.session_state["capital_flow_source_switch"], icon=":material/swap_horiz:")
    capture_diagnostics = pd.DataFrame(st.session_state.get("capital_flow_capture_diagnostics", []))
    if not capture_diagnostics.empty:
        with st.expander(f"最近一次采集诊断｜{st.session_state.get('capital_flow_capture_diagnostics_time', '')}"):
            tracked_diagnostics = capture_diagnostics.loc[capture_diagnostics["行业"].ne("（未匹配）")]
            missing_diagnostics = tracked_diagnostics.loc[tracked_diagnostics["状态"].ne("已采集")]
            if missing_diagnostics.empty:
                st.success(f"{len(CAPITAL_FLOW_SECTORS)} 个关注板块均已匹配到有效数据。", icon=":material/check_circle:")
            else:
                st.caption(f"未成功采集 {len(missing_diagnostics)} 个关注板块。具体状态可以区分源端未返回、源名称未识别和数值无效。")
                st.dataframe(missing_diagnostics, width="stretch", hide_index=True)
            unknown_diagnostics = capture_diagnostics.loc[capture_diagnostics["状态"].eq("源名称未识别")]
            if not unknown_diagnostics.empty:
                st.caption(f"另外发现 {len(unknown_diagnostics)} 个未自动归类的源标签，按来源和名称排序供核对；不会自动当成目标板块。")
                st.dataframe(unknown_diagnostics.sort_values(["预期来源", "源标签"]), width="stretch", hide_index=True, height=320)
    st.caption("资金数据为对应来源发布的行业及概念资金净额快照；东方财富与同花顺口径可能不同。5 分钟采样用于观察同一来源的日内变化，不代表逐笔真实资金，也不用于自动交易。")
    replay = normalize_capital_replay(replay)
    timestamps = sorted(replay.get("时间", pd.Series(dtype=str)).dropna().astype(str).loc[lambda values: values.str.strip().ne("")].unique().tolist())
    replay_dates = sorted({timestamp[:10] for timestamp in timestamps if len(timestamp) >= 10})
    st.subheader("回放数据完整度", icon=":material/fact_check:")
    if hasattr(st, "fragment"):
        st.caption("后台独立采集已配置；下方每分钟读取本地快照。")

        @st.fragment(run_every="1min")
        def _live_capital_readiness():
            from .public_workspace.pages.capital import render_readiness
            fresh_replay = normalize_capital_replay(load_capital_replay(replay_dir))
            times=fresh_replay.get("时间",pd.Series(dtype=str)).dropna().astype(str)
            dates=sorted({value[:10] for value in times if len(value)>=10})
            selected=st.session_state.get("capital_replay_live_date")
            if selected not in dates: selected=dates[-1] if dates else None
            render_readiness(fresh_replay,selected)

        _live_capital_readiness()

        @st.fragment(run_every="1min")
        def _live_capital_flow_panel():
            fresh_replay = load_capital_replay(replay_dir)
            fresh_times = fresh_replay.get("时间", pd.Series(dtype=str)).dropna().astype(str)
            fresh_dates = sorted({value[:10] for value in fresh_times if len(value) >= 10})
            if not fresh_dates:
                st.info("正在等待第一次成功采集。后台将在交易时段每 5 分钟尝试获取一次；也可点击“现在采集一次”。", icon=":material/info:")
                return
            date_key = "capital_replay_live_date"
            _follow_latest_replay_date(date_key, fresh_dates)
            selected_live_date = st.selectbox("走势交易日", fresh_dates, index=fresh_dates.index(st.session_state[date_key]), key=date_key)
            fresh_day = filter_capital_replay_by_date(fresh_replay, selected_live_date)
            _render_intraday_flow_charts(fresh_day)

        _live_capital_flow_panel()
    else:
        from .public_workspace.pages.capital import render_readiness
        render_readiness(replay,replay_dates[-1] if replay_dates else None,track_label="行业资金轨迹")
        if replay_dates:
            _render_intraday_flow_charts(filter_capital_replay_by_date(replay, replay_dates[-1]))
    from .public_workspace.pages.capital import render_research_links
    render_research_links(stocks,_owner_sector_navigation(stocks,"板块资金流向"))
    with st.container(border=True):
        st.subheader("导入历史资金回放", icon=":material/upload_file:")
        upload = st.file_uploader("上传行业资金回放文件", type=["csv", "xlsx", "xls"], key="capital_replay_upload")
        st.download_button(
            "下载资金回放模板",
            capital_replay_template().to_csv(index=False, encoding="utf-8-sig"),
            "行业资金回放模板.csv",
            "text/csv",
            icon=":material/download:",
        )
        st.caption("模板字段：时间、行业、净流入额、涨跌幅、成交额、领涨股、样本数。单一收盘快照可生成收盘偏好排行；多个时间点才可生成全天曲线。")
        if upload is not None:
            try:
                uploaded_frame = normalize_capital_replay(read_tabular_upload(upload.getvalue(), upload.name))
                errors = validate_capital_replay(uploaded_frame)
                if errors:
                    st.error("；".join(errors))
                else:
                    st.success(f"文件校验通过：{len(uploaded_frame):,} 行，{uploaded_frame['时间'].nunique():,} 个时点。")
                    st.dataframe(uploaded_frame.head(40), width="stretch", hide_index=True)
                    if st.button("保存资金回放快照", icon=":material/save:", key="save_capital_replay"):
                        path = save_capital_replay(uploaded_frame, replay_dir)
                        st.success(f"已保存：{path}")
                        st.rerun()
            except Exception as exc:
                st.error(str(exc))
    if not timestamps:
        st.info("当前还没有已保存的资金快照。后台会在交易时段尝试采集，也可使用上方“现在采集一次”。", icon=":material/info:")
    else:
        _follow_latest_replay_date("capital_replay_date", replay_dates)
        selected_date = st.selectbox("回放交易日", replay_dates, index=len(replay_dates) - 1, key="capital_replay_date")
        day_replay = filter_capital_replay_by_date(replay, selected_date)
        detail_segments = _capital_replay_segments(day_replay)
        with st.container(border=True):
            st.subheader("选定时点明细与行业资金地图", icon=":material/paid:")
            day_timestamps = sorted(day_replay["时间"].astype(str).unique().tolist())
            if st.session_state.get("capital_replay_time") not in day_timestamps:
                st.session_state["capital_replay_time"] = day_timestamps[-1]
            selected_time = st.selectbox("回放时点", day_timestamps, index=len(day_timestamps) - 1, key="capital_replay_time")
            detail_label, detail_replay = next(
                ((label, group) for label, group in reversed(detail_segments)
                 if group["时间"].astype(str).eq(selected_time).any()),
                detail_segments[-1],
            )
            if len(detail_segments) > 1:
                st.caption(f"当前时点属于 {detail_label}；下方全天轨迹和变化榜仅比较这一资金源片段。")
            snapshot = detail_replay.loc[detail_replay["时间"].astype(str).eq(selected_time)].copy()
            snapshot["净流入额"] = pd.to_numeric(snapshot["净流入额"], errors="coerce")
            snapshot = snapshot.dropna(subset=["净流入额"]).sort_values("净流入额", ascending=False)
            ranked = snapshot.head(20).copy()
            with st.container(horizontal=True):
                st.metric("当前时点", selected_time, border=True)
                st.metric("净流入行业", int((snapshot["净流入额"] > 0).sum()), border=True)
                st.metric("净流出行业", int((snapshot["净流入额"] < 0).sum()), border=True)
                st.metric("合计净流入", f"{snapshot['净流入额'].sum() / 1e8:+.2f} 亿", border=True)
            chart_data = ranked.loc[:, ["行业", "净流入额"]].set_index("行业")
            map_frame = capital_replay_snapshot_map(snapshot)
            if not map_frame.empty and map_frame["面积"].gt(0).any():
                with st.container(border=True):
                    st.subheader("行业资金地图", icon=":material/grid_view:")
                    st.caption("面积优先使用成交额；缺少成交额时使用资金净流入绝对值。红色表示净流入，绿色表示净流出。")
                    map_hover = [field for field in ["净流入额", "成交额", "涨跌幅", "领涨股"] if field in map_frame.columns]
                    capital_map = px.treemap(
                        map_frame,
                        path=["行业"],
                        values="面积",
                        color="净流入额",
                        color_continuous_scale=["#16a34a", "#334155", "#ef4444"],
                        color_continuous_midpoint=0,
                        hover_data=map_hover,
                    )
                    capital_map.update_layout(height=460, margin=dict(t=8, l=0, r=0, b=0), coloraxis_colorbar_title="净流入")
                    st.plotly_chart(capital_map, width="stretch")
            st.bar_chart(chart_data, horizontal=True, color="#ef4444")
            st.dataframe(
                ranked,
                column_config={
                    "净流入额": st.column_config.NumberColumn("净流入额", format="%.0f"),
                    "涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%.2f%%"),
                    "成交额": st.column_config.NumberColumn("成交额", format="compact"),
                    "样本数": st.column_config.NumberColumn("样本数", format="%,d"),
                },
                width="stretch",
                hide_index=True,
            )
            available_industries = snapshot["行业"].dropna().astype(str).loc[lambda values: values.str.strip().ne("")].tolist()
            if available_industries:
                tracked_industry = st.selectbox("查看单一行业全天轨迹", available_industries, key="capital_replay_industry")
                track = capital_replay_industry_track(detail_replay, tracked_industry)
                if len(track) > 1:
                    with st.container(border=True):
                        st.subheader(f"{tracked_industry} 资金轨迹", icon=":material/show_chart:")
                        st.caption("净流入额为每个导入时点的快照值；并非系统推算的逐笔资金数据。")
                        st.line_chart(track, x="时间", y="净流入额", color="#ef4444")
                else:
                    st.info(f"{tracked_industry} 当前只有一个时点，继续导入更多时点后即可生成全天轨迹。", icon=":material/info:")
            changes = capital_replay_flow_changes(detail_replay)
            if not changes.empty:
                with st.container(border=True):
                    st.subheader("行业资金变化榜", icon=":material/swap_vert:")
                    st.caption("对比当前已导入数据中最早与最晚时点的净流入额变化；只统计两个时点都存在的行业。")
                    change_left, change_right = st.columns(2, vertical_alignment="top")
                    with change_left:
                        st.markdown("**流入改善靠前**")
                        st.dataframe(
                            changes.head(10),
                            column_config={
                                "首时点净流入": st.column_config.NumberColumn("首时点净流入", format="%.0f"),
                                "末时点净流入": st.column_config.NumberColumn("末时点净流入", format="%.0f"),
                                "净流入变化": st.column_config.NumberColumn("净流入变化", format="%.0f"),
                            },
                            width="stretch",
                            hide_index=True,
                        )
                    with change_right:
                        st.markdown("**流出加剧靠前**")
                        st.dataframe(
                            changes.sort_values("净流入变化").head(10),
                            column_config={
                                "首时点净流入": st.column_config.NumberColumn("首时点净流入", format="%.0f"),
                                "末时点净流入": st.column_config.NumberColumn("末时点净流入", format="%.0f"),
                                "净流入变化": st.column_config.NumberColumn("净流入变化", format="%.0f"),
                            },
                            width="stretch",
                            hide_index=True,
                        )
    if not stocks.empty and {"涨跌幅", "成交额"}.issubset(stocks.columns):
        hierarchy = select_market_group_column(stocks)
        if hierarchy in stocks.columns:
            proxy = stocks.copy()
            proxy["涨跌幅"] = pd.to_numeric(proxy["涨跌幅"], errors="coerce")
            proxy["成交额"] = pd.to_numeric(proxy["成交额"], errors="coerce").fillna(0)
            proxy = proxy.loc[market_group_display_mask(proxy, hierarchy)].copy()
            close_view = proxy.groupby(hierarchy, dropna=False).agg(平均涨跌=("涨跌幅", "mean"), 成交额=("成交额", "sum"), 股票数=("涨跌幅", "size")).reset_index()
            close_view = researchable_market_groups(close_view.rename(columns={"股票数": "股票数"}), minimum_samples=3)
            if not close_view.empty:
                with st.container(border=True):
                    st.subheader("收盘行业强弱参考", icon=":material/monitoring:")
                    st.caption("以下来自当前收盘个股快照的涨跌与成交额汇总，不等同于行业真实资金净流入。")
                    st.dataframe(
                        _ashare_change_style(close_view.sort_values("成交额", ascending=False).head(20)),
                        column_config={
                            "平均涨跌": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
                            "成交额": st.column_config.NumberColumn("成交额", format="compact"),
                            "股票数": st.column_config.NumberColumn("样本数", format="%,d"),
                        },
                        width="stretch",
                        hide_index=True,
                    )


def render_public_page(page, data):
    if page == "热点舆情":
        from .market_sentiment import render_market_sentiment_page
        render_market_sentiment_page(data)
        return
    if page == "板块细分":
        from .sector_directory import render_sector_directory
        render_sector_directory(data)
        return
    if page not in {"市场总览", "盘中选股", "大盘云图", "个股详情", "热点舆情"} and data.get("source_notice"):
        st.caption(data["source_notice"])
    if page not in {"市场总览", "盘中选股", "大盘云图", "个股详情", "热点舆情"}:
        quality = import_quality_report(data.get("stocks"))
        st.caption(f"研究数据状态：{quality['rows']:,} 行｜有效行情覆盖 {quality['coverage'].get('涨跌幅', 0):.1%}｜快照数据，非实时行情")
    if page == "\u5e02\u573a\u603b\u89c8":
        render_market_overview(data)
        return
    if page == "大盘云图":
        render_market_terminal(data)
        return
    {"指数分析":render_index_analysis,"概念排行":render_concept_ranking,"盘中选股":render_intraday_scanner,"板块热力图":render_sector_heatmap,"产业链分层":render_industry_chain,"个股详情":render_stock_detail,"板块资金流向":render_capital_replay}[page](data)
