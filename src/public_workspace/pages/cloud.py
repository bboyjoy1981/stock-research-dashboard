"""Final original all-market cloud, with injected observations/capabilities/navigation."""
import pandas as pd
import plotly.express as px
import streamlit as st
from ...calculations import (market_map_area_options,market_map_leaves,limit_market_map_leaves,
    market_research_queue,market_component_extremes,market_change_distribution,market_activity_concentration,
    market_snapshot_trend,market_history_coverage,market_close_temperature,market_trend_summary,sector_rotation_board,
    research_context_label)
from ...cloud_scope import cloud_scope_summary,cloud_scope_export,cloud_scope_audit
from ...industry_cloud import industry_cloud_figure
from ..cloud_model import market_map_hierarchy_path
from ..market_groups import market_group_display_mask,researchable_market_groups
from ..detail_model import market_group_coverage,quote_export,_ashare_change_style
from ..scanner_model import select_market_group_column
from ..contracts import PublicSnapshot
from .stock_detail import quote_origin
from .cloud_components import (display_table,reset_scope,open_stock_widget,focus_sector,render_sector_lens,
    render_exact_cloud_scope as exact_scope,render_cloud_components as components)


def render(snapshot,capabilities,navigation):
    snapshot=PublicSnapshot(snapshot.stocks,snapshot.indices,dict(snapshot.metadata),dict(snapshot.optional))
    history=snapshot.optional.get('history')
    observed=history.frame.copy() if history is not None else pd.DataFrame()
    observed=pd.concat([observed,snapshot.stocks.assign(快照日期=snapshot.metadata['date'],快照来源=snapshot.metadata['source'])],ignore_index=True)
    data=dict(stocks=snapshot.stocks,index_snapshot=snapshot.indices,import_date=snapshot.metadata['date'],
        stock_quote_source='imported',public_source=snapshot.metadata['source'],market_history=observed)
    render_frame(data,capabilities,navigation,navigation.namespace+'_')

def render_frame(data,capabilities,navigation,prefix=""):
    """Reference-style all-market terminal: central map, right rail and drill-down."""

    state=navigation.state
    def table(frame,**kwargs):
        return display_table(frame,capabilities,**kwargs)
    def download(*args,**kwargs):
        if capabilities.download: return st.download_button(*args,**kwargs)
    def render_exact_cloud_scope(grouped,hierarchy,parent=None):
        return exact_scope(grouped,hierarchy,parent,capabilities,navigation,prefix)
    def render_cloud_components(leaves,hierarchy,size_field):
        return components(leaves,hierarchy,size_field,capabilities,navigation,prefix)
    def _reset_terminal_preset_controls():
        for key in ("terminal_size","terminal_level","terminal_color","terminal_minimum"):
            state.pop(prefix+key,None)
    def _clear_terminal_industry_context():
        reset_scope(state,prefix)
        for key in ("terminal_industry_query","terminal_drilldown_context"):
            state[prefix+key]=""
        state[prefix+"terminal_quick_group"]="全市场"
        state.pop(prefix+"research_context",None)
    def _set_terminal_research_context(target,source="大盘云图 · 市场脉冲"):
        if not isinstance(target,str) or target not in set(grouped[hierarchy].dropna().astype(str)): return
        state[prefix+"terminal_industry_query"]=target
        state[prefix+"research_context"]=dict(source=source,industry=target,field=hierarchy)
    def _focus_from_widget(key,source):
        _set_terminal_research_context(state.get(key),source)
    def _focus_cloud_group():
        target=state.get(prefix+"terminal_quick_group")
        if target=="全市场": _clear_terminal_industry_context()
        else: _set_terminal_research_context(target)
    def render_context():
        label=research_context_label(state.get(prefix+"research_context",{}))
        if label:
            with st.container(horizontal=True):
                st.info(label,icon=":material/route:")
                st.button("定位云图",icon=":material/account_tree:",key=prefix+"research_path_cloud_terminal",
                    on_click=navigation.open_page,args=("大盘云图",))
                st.button("查看同业",icon=":material/query_stats:",key=prefix+"research_path_peers_terminal",
                    on_click=navigation.open_page,args=("个股详情",))
                st.button("清除路径",icon=":material/close:",key=prefix+"clear_research_context_terminal",
                    on_click=_clear_terminal_industry_context)

    # Validate an incoming exact path against the supplied public stock scope.
    frame=data.get("stocks",pd.DataFrame())
    field=state.get(navigation.namespace+"_sector_field")
    value=state.get(navigation.namespace+"_sector")
    parent=state.get(navigation.namespace+"_sector_parent")
    token=(field,parent,value,state.get(navigation.namespace+'_sector_revision'))
    if token!=state.get(prefix+"cloud_synced_sector") and field in ('行业','细分行业','板块') and field in frame:
        valid=frame[field].eq(value)
        if field=='细分行业':
            valid &= frame['行业'].eq(parent) if '行业' in frame else False
        if valid.any():
            state[prefix+"terminal_level"]=field
            state[prefix+"core_cloud_group"]=value
            state[prefix+"core_cloud_parent"]=parent if field=='细分行业' else '全部'
            state[prefix+"cloud_synced_sector"]=token

    stocks = data.get("stocks", pd.DataFrame()).copy()
    sectors = data.get("sectors", pd.DataFrame()).copy()
    if stocks.empty or "涨跌幅" not in stocks.columns:
        st.warning("当前没有可用全市场行情，请先在数据导入页面保存含涨跌幅的全市场快照。")
        return
    st.subheader("大盘云图 · 全市场研究地图", icon=":material/account_tree:")
    render_context()
    stocks = stocks.loc[:, ~stocks.columns.duplicated()].copy()
    stocks["涨跌幅"] = pd.to_numeric(stocks["涨跌幅"], errors="coerce")
    for field in ("成交额", "总市值", "流通市值"):
        if field in stocks.columns:
            stocks[field] = pd.to_numeric(stocks[field], errors="coerce")
    size_options = market_map_area_options(stocks)
    presets = {
        "全市场": ("成交额", "行业", "平均涨跌幅", 1),
        "行业强弱": ("成交额", "行业", "行业强度", 1),
        "细分机会": ("成交额", "细分行业", "平均涨跌幅", 3),
        "市值结构": ("流通市值", "行业", "上涨占比", 1),
    }
    cloud_settings = st.expander("云图设置 · 视角、工作区与更多筛选", expanded=False, icon=":material/tune:")
    with cloud_settings:
        preset_col, workspace_col = st.columns([2.2, 1], vertical_alignment="bottom")
    with preset_col:
        preset_name = st.segmented_control(
            "云图视角", list(presets), default="全市场", key=prefix+"terminal_preset",
            on_change=_reset_terminal_preset_controls,
        ) or "全市场"
    with workspace_col:
        workspace_mode = st.segmented_control(
            "工作区", options=["一屏云图", "深度研究"], default="一屏云图",
            key=prefix+"terminal_workspace_mode",
            help="一屏云图优先显示市场地图与右侧统计；深度研究展示行业排行、轮动和成分股。",
        )
    if preset_name not in presets or workspace_mode not in ("一屏云图","深度研究"):
        st.warning("云图选项无效。")
        return
    preset_size, preset_level, preset_color, preset_minimum = presets[preset_name]
    controls = cloud_settings.columns(3, vertical_alignment="bottom")
    with controls[0]:
        default_size_index = size_options.index(preset_size) if preset_size in size_options else 0
        size_field = st.selectbox("云图面积", size_options, index=default_size_index, key=prefix+"terminal_size")
    preferred_hierarchy = select_market_group_column(stocks)
    hierarchy_options = [field for field in ("细分行业", "行业", "板块") if field in stocks.columns and market_group_coverage(stocks, field)["coverage"] >= 0.15]
    if not hierarchy_options:
        hierarchy_options = [preferred_hierarchy]
    with controls[1]:
        hierarchy = st.selectbox("云图层级", hierarchy_options, index=hierarchy_options.index(preset_level) if preset_level in hierarchy_options else 0, key=prefix+"terminal_level")
    with controls[2]:
        color_modes = ["平均涨跌幅", "上涨占比", "行业强度"]
        color_mode = st.selectbox("云图颜色", color_modes, index=color_modes.index(preset_color), key=prefix+"terminal_color")
    with cloud_settings:
        filter_cols = st.columns(2, vertical_alignment="bottom")
        with filter_cols[0]:
            minimum_size = st.number_input("最小行业样本数", min_value=1, max_value=100, value=preset_minimum, step=1, key=prefix+"terminal_minimum")
            include_unclassified = st.toggle(
                "云图显示未分类样本", value=True, key=prefix+"terminal_include_unclassified",
                help="关闭时，地图只展示有有效行业分类的公司；市场宽度仍使用全部样本。",
            )
        with filter_cols[1]:
            industry_query = st.text_input("筛选行业或细分行业", placeholder="例如：半导体、PCB、银行", key=prefix+"terminal_industry_query", persist_state="session")
            leaf_density = st.segmented_control(
                "云图个股密度", options=["均衡", "完整"], default="完整",
                key=prefix+"terminal_leaf_density",
                help="均衡模式优先保留各行业中最活跃的个股，以提高标签可读性。",
            )
            map_height = st.selectbox(
                "地图高度", [520, 680, 840], index=1, key=prefix+"terminal_map_height",
                format_func=lambda height: {520: "紧凑 · 520", 680: "标准 · 680", 840: "大屏 · 840"}[height],
            )
    if size_field not in size_options or hierarchy not in hierarchy_options or color_mode not in color_modes or leaf_density not in ("紧凑","完整") or map_height not in (520,680,840) or type(minimum_size) is not int or not 1<=minimum_size<=100 or type(include_unclassified) is not bool or not isinstance(industry_query,str):
        st.warning("云图筛选选项无效。")
        return
    if industry_query.strip():
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(f"已定位：{industry_query.strip()}", icon=":material/filter_alt:", color="blue")
            st.button("清除行业定位", icon=":material/filter_alt_off:", key=prefix+"terminal_clear_industry", on_click=_clear_terminal_industry_context)
    if hierarchy not in stocks.columns:
        hierarchy = "板块" if "板块" in stocks.columns else stocks.columns[0]
    path = market_map_hierarchy_path(stocks, hierarchy)
    parent = path[0] if len(path) > 1 else None
    for field in path:
        stocks[field] = stocks[field].fillna("未分类").astype(str).replace("", "未分类")
    if size_field == "等权":
        stocks["等权"] = 1.0
        st.info("导入快照缺少可用成交额及市值，地图改为每只股票等面积展示；面积不代表资金或市值。")
    valid_stocks = stocks.loc[stocks["涨跌幅"].notna()].copy()
    grouped = valid_stocks.groupby(path, dropna=False).agg(
        成交额=(size_field, "sum"),
        涨跌幅=("涨跌幅", "mean"),
        股票数=("涨跌幅", "size"),
        上涨占比=("涨跌幅", lambda values: float((values > 0).mean()) if values.notna().any() else 0),
    ).reset_index()
    grouped = grouped.loc[grouped["股票数"] >= int(minimum_size)].copy()
    if grouped.empty:
        st.warning("当前筛选条件下没有可展示的行业，请调低最小行业样本数。")
        return
    if size_field == "等权":
        grouped["行业强度"] = (grouped["涨跌幅"].rank(pct=True).fillna(0) * 65 + grouped["上涨占比"].rank(pct=True).fillna(0) * 35).round(0)
    else:
        grouped["行业强度"] = (grouped["涨跌幅"].rank(pct=True).fillna(0) * 55 + grouped["上涨占比"].rank(pct=True).fillna(0) * 30 + grouped["成交额"].rank(pct=True).fillna(0) * 15).round(0)
    display_grouped = grouped.copy()
    classified_stock_mask = market_group_display_mask(stocks, hierarchy)
    classification = market_group_coverage(stocks, hierarchy)
    classified_stock_count = classification["classified"]
    if not include_unclassified and not industry_query.strip():
        classified_group_mask = market_group_display_mask(display_grouped, hierarchy)
        if bool(classified_group_mask.any()):
            display_grouped = display_grouped.loc[classified_group_mask].copy()
    if industry_query.strip():
        query = industry_query.strip()
        match = display_grouped[hierarchy].astype(str).str.contains(query, case=False, regex=False, na=False)
        if parent:
            match = match | display_grouped[parent].astype(str).str.contains(query, case=False, regex=False, na=False)
        display_grouped = display_grouped.loc[match].copy()
    if not display_grouped.empty:
        display_grouped = render_exact_cloud_scope(display_grouped, hierarchy, parent)
    if display_grouped.empty:
        st.warning("没有匹配到行业或细分行业，请调整筛选关键词。")
        return
    ranking_minimum = max(3, int(minimum_size))
    ranking_grouped = researchable_market_groups(display_grouped, minimum_samples=ranking_minimum)
    if ranking_grouped.empty:
        ranking_grouped = display_grouped.copy()
    rank_config = {
        "涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
        "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
        "成交额": st.column_config.NumberColumn("等权样本数" if size_field == "等权" else f"{size_field}规模", format="compact"),
        "股票数": st.column_config.NumberColumn("样本数", format="%,d"),
        "行业强度": st.column_config.ProgressColumn("行业强度", min_value=0, max_value=100, format="%d 分"),
    }
    color_field = {"平均涨跌幅": "涨跌幅", "上涨占比": "上涨占比", "行业强度": "行业强度"}[color_mode]
    metric_source = grouped["涨跌幅"].dropna()
    up_count = int((stocks["涨跌幅"] > 0).sum())
    down_count = int((stocks["涨跌幅"] < 0).sum())
    flat_count = int(stocks["涨跌幅"].eq(0).sum())
    limit_up = int((stocks["涨跌幅"] >= 9.8).sum())
    limit_down = int((stocks["涨跌幅"] <= -9.8).sum())
    median_change = float(stocks["涨跌幅"].median()) if stocks["涨跌幅"].notna().any() else 0.0
    strength = max(0, min(100, round(50 + (up_count - down_count) / max(len(valid_stocks), 1) * 50)))
    market_state = "普涨" if up_count > down_count * 1.5 else "普跌" if down_count > up_count * 1.5 else "分化"
    scope_note = (
        f"有效分类 {classified_stock_count:,}/{len(stocks):,} 只；未分类已隐藏，可在更多筛选中查看。"
        if not include_unclassified and classified_stock_count < len(stocks)
        else f"导入全市场 {len(stocks):,} 只；地图按当前分类筛选，仅绘制涨跌与面积有效的样本，实际数量见右侧。"
    )
    st.caption(f"{quote_origin(data)} · 非实时｜红涨绿跌 · 面积={'每股等权' if size_field == '等权' else size_field} · {scope_note}")
    if workspace_mode == "深度研究":
      with st.container(horizontal=True):
        if st.button("查看市场总览", icon=":material/dashboard:", key=prefix+"terminal_open_overview"):
            navigation.open_page("市场总览")
            st.rerun()
        if st.button("进入个股详情", icon=":material/description:", key=prefix+"terminal_open_detail"):
            navigation.open_page("个股详情")
            st.rerun()
      with st.container(horizontal=True):
        st.metric("市场样本", f"{len(stocks):,}", border=True)
        st.metric("上涨 / 下跌", f"{up_count:,} / {down_count:,}", border=True)
        st.metric("平均涨跌", f"{metric_source.mean():+.2f}%" if not metric_source.empty else "暂无", border=True)
        st.metric("涨幅超过 5%", int((stocks["涨跌幅"] >= 5).sum()), border=True)
    if workspace_mode == "深度研究" and not ranking_grouped.empty and size_field != "等权":
        pulse_leader = ranking_grouped.sort_values(["行业强度", "成交额"], ascending=[False, False]).iloc[0]
        pulse_active = ranking_grouped.sort_values("成交额", ascending=False).iloc[0]
        with st.container(border=True):
            st.subheader("云图市场脉冲", icon=":material/podcasts:")
            st.caption("用当前云图的行业强度与规模活跃度提炼首要验证线索；结果基于导入快照，不预测后续行情。")
            with st.container(horizontal=True):
                st.metric("强势验证", str(pulse_leader[hierarchy]), f"强度 {pulse_leader['行业强度']:.0f}/100", border=True)
                st.metric("规模活跃", str(pulse_active[hierarchy]), f"{size_field} {pulse_active['成交额'] / 1e8:.2f} 亿", border=True)
                st.metric("市场宽度", f"{up_count / max(len(valid_stocks), 1):.0%}", "有效行情上涨占比", border=True)
            with st.container(horizontal=True):
                st.button(
                    f"定位强势{hierarchy}",
                    icon=":material/center_focus_strong:",
                    key=prefix+"terminal_pulse_leader",
                    on_click=_set_terminal_research_context,
                    args=(pulse_leader[hierarchy],),
                )
                st.button(
                    f"定位活跃{hierarchy}",
                    icon=":material/local_fire_department:",
                    key=prefix+"terminal_pulse_active",
                    on_click=_set_terminal_research_context,
                    args=(pulse_active[hierarchy],),
                )
        research_queue = market_research_queue(ranking_grouped, hierarchy)
        if workspace_mode == "深度研究" and not research_queue.empty:
            with st.container(border=True):
                st.subheader("云图研究清单", icon=":material/playlist_add_check:")
                st.caption("从当前行业快照中分别提取强度领先、规模活跃和相对市场偏离的核对对象；用于决定下一步研究路径，不构成交易建议。")
                table(
                    _ashare_change_style(research_queue),
                    column_config={
                        "涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
                        "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
                        "成交额": st.column_config.NumberColumn("规模", format="compact"),
                        "行业强度": st.column_config.ProgressColumn("行业强度", min_value=0, max_value=100, format="%d 分"),
                        "相对市场": st.column_config.NumberColumn("相对市场", format="%+.2f%%"),
                    },
                    width="stretch",
                    hide_index=True,
                )
                queue_options = research_queue[hierarchy].astype(str).tolist()
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    queue_target = st.selectbox("定位清单行业", queue_options, key=prefix+"terminal_queue_target")
                    st.button("在云图中定位", icon=":material/center_focus_strong:", key=prefix+"terminal_queue_focus",
                              on_click=_focus_from_widget, args=(prefix+"terminal_queue_target", "大盘云图 · 研究清单"))
    if workspace_mode == "深度研究":
      with st.container(horizontal=True):
        st.metric(f"有效{hierarchy}", f"{classification['classified']:,}", border=True)
        st.metric("未分类样本", f"{classification['unclassified']:,}", border=True)
        st.metric("分类覆盖率", f"{classification['coverage']:.1%}", border=True)
        st.metric("可研究分类", f"{len(ranking_grouped):,}", border=True)
      pulse_left, pulse_right = st.columns([2.5, 1], vertical_alignment="center")
      with pulse_left:
          st.progress(strength / 100, text=f"市场强弱 {strength}/100：上涨 {up_count:,} 家｜下跌 {down_count:,} 家｜平盘 {flat_count:,} 家")
      with pulse_right:
          st.caption(f"极端波动：+9.8% 以上 {limit_up:,} 家；-9.8% 以下 {limit_down:,} 家")
    cloud_tabs = st.tabs(['全市场云图', '行业研究', '导出核对'], key=prefix+'cloud_workspace', on_change='rerun')
    with cloud_tabs[0]:
        left, right = st.columns([4, 1.25], vertical_alignment="top")
    with left:
        with st.container(border=True):
            st.subheader(f"全市场 · {hierarchy}地图", icon=":material/account_tree:")
            map_detail = st.segmented_control('地图内容', ['板块', '个股'], default='板块', key=prefix+'terminal_map_detail') or '板块'
            if map_detail not in ('板块','个股'):
                st.warning("地图粒度无效。")
                return
            quick_groups = grouped.loc[market_group_display_mask(grouped, hierarchy), hierarchy].dropna().astype(str).unique().tolist()
            with st.expander("关键词定位与全市场重置", expanded=False):
                quick_controls = st.columns([3, 1, 1], vertical_alignment="bottom")
            with quick_controls[0]:
                quick_group = st.selectbox("快速定位行业", ["全市场", *sorted(quick_groups)], key=prefix+"terminal_quick_group", label_visibility="collapsed")
            with quick_controls[1]:
                st.button("定位", icon=":material/center_focus_strong:", key=prefix+"terminal_quick_focus", on_click=_focus_cloud_group, width="stretch")
            with quick_controls[2]:
                st.button("全市场", icon=":material/filter_alt_off:", key=prefix+"terminal_quick_reset", on_click=_clear_terminal_industry_context, width="stretch")
            if color_field == "涨跌幅":
                st.markdown(":green[-3%] · :green[-2%] · :green[-1%] · :gray[0%] · :red[+1%] · :red[+2%] · :red[+3%]")
            else:
                st.caption("绿色表示较低分位，红色表示较高分位；颜色按当前所选指标映射。")
            if parent:
                visible_groups = display_grouped[[parent, hierarchy]].drop_duplicates()
                map_stocks = stocks.merge(visible_groups, on=[parent, hierarchy], how="inner")
            else:
                map_stocks = stocks.loc[stocks[hierarchy].astype(str).isin(display_grouped[hierarchy].astype(str))].copy()
            leaf_frame = market_map_leaves(map_stocks, display_grouped, hierarchy, size_field, color_field, parent_field=parent)
            raw_leaf_count = len(leaf_frame)
            if leaf_density == "均衡" and map_detail == '个股':
                leaf_frame = limit_market_map_leaves(leaf_frame, hierarchy, maximum_per_group=18, parent_field=parent)
            visible_scope = cloud_scope_summary(leaf_frame)
            with cloud_tabs[2]:
                st.subheader('地图范围与覆盖核对', icon=':material/fact_check:')
                st.caption(f"交易日 {data.get('import_date') or '未提供'} · 层级 {hierarchy} · 面积 {size_field} · 颜色 {color_mode} · 密度 {leaf_density} · 非实时")
                audit = cloud_scope_audit(map_stocks, size_field, len(leaf_frame))
                with st.container(horizontal=True):
                    st.metric('筛选范围', f"{audit['范围样本']:,}", border=True)
                    st.metric('可绘制 / 实际显示', f"{audit['可绘制样本']:,} / {audit['实际显示']:,}", border=True)
                    st.metric('未知涨跌', f"{audit['未知涨跌']:,}", border=True)
                    st.metric('抽样未显示', f"{audit['抽样未显示']:,}", border=True)
                st.table(audit, border='horizontal', width='stretch')
                st.caption('范围样本已经过行业、关键词及最小样本数筛选；面积无效仅统计涨跌有效但面积非正或缺失的记录。右侧市场强弱仍使用全市场，不混用当前地图范围。')
                audit_export = pd.DataFrame([dict(audit, 快照日期=data.get('import_date') or '未提供', 分类层级=hierarchy, 面积口径=size_field, 密度=leaf_density)])
                download('导出地图覆盖统计', quote_export(audit_export, data).to_csv(index=False).encode('utf-8-sig'),
                                   file_name='cloud_scope_audit.csv', mime='text/csv', key='cloud_audit_export', icon=':material/download:')
            if leaf_frame.empty:
                st.info("当前筛选范围没有可用于个股云图的行情叶子节点。")
            else:
                tree_frame = leaf_frame
                tree_path = [*path, '云图标签']
                if map_detail == '板块':
                    tree_frame = leaf_frame.groupby(path, dropna=False).agg(
                        面积=('面积','sum'), 涨跌幅=('涨跌幅','mean'), 云图颜色=('云图颜色','mean'),
                        成分股数=('个股','size')).reset_index()
                    tree_frame['板块标签'] = tree_frame[hierarchy].astype(str) + '\n' + tree_frame['涨跌幅'].map(lambda change: f'{change:+.2f}%')
                    tree_path = [*path[:-1], '板块标签']
                tree = px.treemap(
                    tree_frame,
                    path=tree_path,
                    values="面积",
                    color="云图颜色",
                    hover_data={**({'成分股数':True} if map_detail == '板块' else {'个股':True}), '涨跌幅':':.2f', '面积':':.2f'},
                    color_continuous_scale=[
                        [0.0, "#0e7248"], [0.46, "#1c513b"], [0.499, "#43505a"],
                        [0.501, "#43505a"], [0.54, "#81343c"], [1.0, "#cf3640"],
                    ],
                    range_color=([-5, 5] if color_field == "涨跌幅" else [0, 1] if color_field == "上涨占比" else [0, 100]),
                )
                tree.update_traces(textinfo="label", marker_line_width=1, marker_line_color="#0b1018", textfont_size=11)
                tree.update_layout(height=map_height, margin=dict(t=4, l=4, r=4, b=4), coloraxis_showscale=False, paper_bgcolor="#0d1522", font_color="#f1f5f9")
                if map_detail == '板块':
                    tree = industry_cloud_figure(tree_frame, tree_path, height=max(720, map_height),
                                                color_range=(-3, 3) if color_field == '涨跌幅' else (0, 1) if color_field == '上涨占比' else (0, 100))
                st.plotly_chart(tree, width="stretch")
                density_note = f"均衡模式显示 {len(leaf_frame):,}/{raw_leaf_count:,} 个叶子节点" if leaf_density == "均衡" and map_detail == '个股' else f"完整模式显示全部 {raw_leaf_count:,} 个叶子节点"
                st.caption(f"{'板块聚合视图；面积汇总成分股，涨跌为等权平均，非行业指数。' if map_detail == '板块' else '个股视图；方块显示名称与涨跌幅。'} 面积为{size_field}，颜色为{color_mode}。{density_note.replace('叶子节点', '成分股样本')}。")
                download(
                    "导出当前地图个股", cloud_scope_export(leaf_frame, date=data.get("import_date"), area=size_field, color=color_mode, source=data.get("stock_quote_source")).to_csv(index=False).encode("utf-8-sig"),
                    "cloud_visible_stocks.csv", "text/csv", key=prefix+"terminal_visible_export", icon=":material/download:",
                )
                with st.expander("地图下钻：定位行业或打开个股", expanded=False, icon=":material/travel_explore:"):
                    drill_cols = st.columns(2, vertical_alignment="bottom")
                    with drill_cols[0]:
                        industry_choices = sorted(display_grouped[hierarchy].dropna().astype(str).unique().tolist())
                        selected_industry = st.selectbox(f"选择{hierarchy}", industry_choices, key=prefix+"terminal_map_industry")
                        st.button("在地图中定位", icon=":material/center_focus_strong:", key=prefix+"terminal_map_focus",
                                  on_click=_set_terminal_research_context, args=(selected_industry, "大盘云图 · 地图下钻"))
                    with drill_cols[1]:
                        stock_choices = leaf_frame.sort_values("面积", ascending=False)["个股"].drop_duplicates().tolist()
                        selected_stock = st.selectbox("选择地图中的个股", stock_choices, key=prefix+"terminal_map_stock")
                        if st.button("打开个股研究卡", icon=":material/open_in_new:", key=prefix+"terminal_map_open_stock"):
                            selected_row = leaf_frame.loc[leaf_frame["个股"].eq(selected_stock)].iloc[0]
                            state[prefix+"stock_detail_query"] = selected_stock.split(" · ", 1)[0]
                            state[prefix+"research_context"] = {"source": "大盘云图 · 地图下钻", "industry": str(selected_row[hierarchy])}
                            navigation.open_page("个股详情")
                            st.rerun()
                with cloud_tabs[1]:
                    render_cloud_components(leaf_frame, hierarchy, size_field)
                    render_sector_lens(map_stocks, hierarchy, data, prefix+'cloud_lens',capabilities,navigation,session_prefix=prefix)
                with cloud_tabs[2]:
                    preview = cloud_scope_export(leaf_frame, date=data.get('import_date'), area=size_field, color=color_mode, source=data.get('stock_quote_source'))
                    fields = [field for field in ('代码', '个股', hierarchy, '涨跌幅', '面积', '快照日期', '行情来源') if field in preview]
                    st.subheader('当前地图导出预览', icon=':material/table_chart:')
                    table(preview[fields].head(100), hide_index=True, width='stretch', height=360)
                    st.caption(f'预览前 {min(100, len(preview))} 条；上方个股导出包含当前显示的全部 {len(preview):,} 个方块，不包含抽样隐藏的股票。')
    with right:
        with st.container(border=True):
            st.subheader("当前地图范围", icon=":material/center_focus_strong:")
            st.caption(industry_query.strip() or "当前分类与样本筛选")
            scope_average = visible_scope["平均涨跌"]
            st.table({"贡献样本": f"{visible_scope['样本']:,} 只",
                      "上涨 / 下跌": f"{visible_scope['上涨']:,} / {visible_scope['下跌']:,}",
                      "平均涨跌": f"{scope_average:+.2f}%" if scope_average is not None else "—"},
                     border="horizontal", width="stretch")
            st.caption("板块模式统计当前筛选范围内的全部有效成分股，不做均衡抽样。下方市场强弱使用全市场有效行情。" if map_detail == '板块' else "仅统计当前显示个股；均衡模式为抽样展示。下方市场强弱仍使用全市场有效行情。")
        with st.container(border=True):
            st.subheader("市场强弱")
            st.table({"上涨": f"{up_count:,} 家", "下跌": f"{down_count:,} 家",
                      "平盘": f"{flat_count:,} 家", "强弱评分": f"{strength}/100"},
                     border="horizontal", width="stretch")
            st.caption(f"中位涨跌 {median_change:+.2f}%｜涨停附近 {limit_up:,}｜跌停附近 {limit_down:,}")
            st.badge(market_state, icon=":material/monitoring:", color="red" if market_state == "普涨" else "green" if market_state == "普跌" else "blue")
            breadth = pd.DataFrame({"方向": ["上涨", "平盘", "下跌"], "数量": [up_count, flat_count, down_count]})
            breadth_chart = px.bar(breadth, x="数量", y="方向", orientation="h", color="方向", color_discrete_map={"上涨":"#ef4444", "平盘":"#64748b", "下跌":"#22c55e"})
            breadth_chart.update_layout(height=155, margin=dict(t=4, l=0, r=0, b=0), showlegend=False, paper_bgcolor="#0d1522", plot_bgcolor="#0d1522", font_color="#dbe5f2")
            st.plotly_chart(breadth_chart, width="stretch")
            st.subheader("涨跌统计", icon=":material/bar_chart:")
            distribution = market_change_distribution(stocks)
            distribution_chart = px.bar(
                distribution,
                x="区间",
                y="数量",
                color="区间",
                color_discrete_map={
                    "<-7%": "#16a34a", "-7%~-3%": "#22c55e", "-3%~0%": "#86efac",
                    "0%": "#64748b", "0%~3%": "#fca5a5", "3%~7%": "#ef4444", ">7%": "#b91c1c",
                },
            )
            distribution_chart.update_layout(height=165, margin=dict(t=4, l=0, r=0, b=0), showlegend=False, paper_bgcolor="#0d1522", plot_bgcolor="#0d1522", font_color="#dbe5f2")
            st.plotly_chart(distribution_chart, width="stretch")
            st.caption("按个股涨跌幅区间统计，用于盘后辨别赚钱效应与亏钱效应的扩散范围。")
            concentration = market_activity_concentration(stocks, size_field="成交额", top_n=10)
            st.subheader("成交结构", icon=":material/donut_small:")
            if concentration["前N成交占比"] is None:
                st.caption("导入文件缺少可用成交额，暂不能统计成交集中度；市值不替代成交额。")
            else:
                st.metric(
                    f"前 {concentration['N']} 只占比",
                    f"{concentration['前N成交占比']:.0%}",
                    f"成交额 {concentration['前N成交额'] / 1e8:.2f} 亿",
                )
                st.progress(concentration["前N成交占比"], text=f"全市场成交额：{concentration['总成交额'] / 1e8:.2f} 亿")
                st.caption("用于盘后观察成交是否集中在少数活跃个股；仅描述导入快照。")
            st.subheader("收盘趋势", icon=":material/timeline:")
            close_trend = market_snapshot_trend(
                data.get("market_history", pd.DataFrame()),
                through_date=data.get("import_date") if data.get("stock_quote_source") == "imported" else None,
            )
            history_coverage = market_history_coverage(close_trend)
            trend_view = st.segmented_control(
                "趋势视角",
                options=["上涨广度", "平均涨跌", "成交额"],
                default="上涨广度",
                key=prefix+"terminal_trend_view",
            )
            if len(close_trend) < 2:
                st.caption(f"当前已保存 {history_coverage['交易日数']} 个有效交易日；至少两个不同交易日后，这里会显示上涨广度与成交额的收盘趋势。")
            else:
                current_trend = close_trend.iloc[-1]
                previous_trend = close_trend.iloc[-2]
                st.metric(
                    "最新上涨占比",
                    f"{current_trend['上涨占比']:.0%}",
                    f"较前一日 {current_trend['上涨占比'] - previous_trend['上涨占比']:+.0%}",
                    delta_color="inverse",
                )
                with st.container(horizontal=True):
                    st.metric("涨停附近", f"{int(current_trend['涨停附近']):,}", f"较前日 {int(current_trend['涨停附近'] - previous_trend['涨停附近']):+,}")
                    st.metric("跌停附近", f"{int(current_trend['跌停附近']):,}", f"较前日 {int(current_trend['跌停附近'] - previous_trend['跌停附近']):+,}", delta_color="inverse")
                temperature = market_close_temperature(current_trend.to_dict())
                st.subheader("收盘情绪", icon=":material/thermostat:")
                st.badge(temperature["状态"], icon=":material/monitoring:", color=temperature["颜色"])
                st.caption(temperature["说明"])
                trend_column = {"上涨广度": "上涨占比", "平均涨跌": "平均涨跌", "成交额": "成交额"}[trend_view]
                if trend_view == "成交额" and not close_trend["成交额"].notna().any():
                    st.info("已保存快照未提供成交额，不能绘制成交趋势。")
                else:
                    st.line_chart(close_trend.set_index("交易日")[trend_column], height=150)
                latest_amount = f"{current_trend['成交额'] / 1e8:.2f} 亿" if pd.notna(current_trend["成交额"]) else "未提供"
                st.caption(f"最新成交额 {latest_amount}｜样本 {int(current_trend['样本数']):,} 只")
                partial_amount_days = close_trend.loc[close_trend["成交额有效数"] < close_trend["样本数"], "交易日"]
                if not partial_amount_days.empty:
                    st.caption(f"成交额数据不完整：{len(partial_amount_days)} 个交易日存在缺失值，金额仅计入已提供的股票。")
                st.caption(f"趋势覆盖 {history_coverage['交易日数']} 个交易日：{history_coverage['起始日']} 至 {history_coverage['截至日']}。")
                trend_summary = market_trend_summary(close_trend)
                with st.container(horizontal=True):
                    st.metric("期间最高广度", f"{trend_summary['最高广度']:.0%}", border=True)
                    st.metric("期间最低广度", f"{trend_summary['最低广度']:.0%}", border=True)
                    st.metric("日均成交额", f"{trend_summary['平均成交额'] / 1e8:.2f} 亿" if trend_summary["平均成交额"] is not None else "未提供", border=True)
                with st.expander("查看已保存收盘快照", expanded=False):
                    table(
                        close_trend.sort_values("交易日", ascending=False),
                        column_config={
                            "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
                            "平均涨跌": st.column_config.NumberColumn("平均涨跌", format="%+.2f%%"),
                            "成交额": st.column_config.NumberColumn("成交额", format="compact"),
                            "样本数": st.column_config.NumberColumn("样本数", format="%,d"),
                        },
                        width="stretch",
                        hide_index=True,
                    )
                    download(
                        "导出收盘趋势 CSV",
                        close_trend.to_csv(index=False).encode("utf-8-sig"),
                        file_name="市场收盘趋势.csv",
                        mime="text/csv",
                        icon=":material/download:",
                    )
            st.subheader(f"活跃{hierarchy}")
            active = ranking_grouped.sort_values("成交额", ascending=False).head(8)
            table(_ashare_change_style(active[[hierarchy, "成交额", "涨跌幅", "股票数"]]), column_config=rank_config, width="stretch", hide_index=True)
            st.caption(f"颜色可切换为平均涨跌、上涨占比或行业强度；面积始终反映所选规模指标。排行默认要求至少 {ranking_minimum} 只样本，{hierarchy}为空的记录不会伪造分类。")
            indices = data.get("index_snapshot", pd.DataFrame()).copy()
            if not indices.empty and {"名称", "涨跌幅"}.issubset(indices.columns):
                indices["涨跌幅"] = pd.to_numeric(indices["涨跌幅"], errors="coerce")
                indices = indices.loc[indices['名称'].ne('北证50')].rename(columns={'价格':'点位'})
                index_columns = [field for field in ("名称", "点位", "涨跌幅") if field in indices.columns]
                st.subheader("核心指数 · 收盘快照")
                table(indices.dropna(subset=["涨跌幅"]).head(8)[index_columns], width="stretch", hide_index=True)
                source_dates=sorted(set(indices['交易日期'].dropna().astype(str))) if '交易日期' in indices else []
                source_labels=sorted(set(indices['来源'].dropna().astype(str))) if '来源' in indices else []
                st.caption("指数交易日："+"、".join(source_dates or ['未提供'])+"｜指数来源："+"、".join(source_labels or ['未提供'])+"｜各自来源日期，不借用个股日期；非实时。")

    if workspace_mode == "一屏云图":
        st.caption("当前为一屏云图模式：地图下方可展开当前成分股并直接研究；如需完整排行、行业轮动或资金联动，可在云图设置中切换至“深度研究”。")
        return

    rank_left, rank_mid, rank_right = st.columns(3, vertical_alignment="top")
    rank_columns = [hierarchy, "涨跌幅", "上涨占比", "成交额", "股票数", "行业强度"]
    with rank_left:
        with st.container(border=True):
            st.subheader(f"领涨{hierarchy}")
            table(_ashare_change_style(ranking_grouped.sort_values("涨跌幅", ascending=False).head(10)[rank_columns]), column_config=rank_config, width="stretch", hide_index=True)
    with rank_mid:
        with st.container(border=True):
            st.subheader(f"领跌{hierarchy}")
            table(_ashare_change_style(ranking_grouped.sort_values("涨跌幅").head(10)[rank_columns]), column_config=rank_config, width="stretch", hide_index=True)
    with rank_right:
        with st.container(border=True):
            st.subheader(f"高强度{hierarchy}")
            table(_ashare_change_style(ranking_grouped.sort_values("行业强度", ascending=False).head(10)[rank_columns]), column_config=rank_config, width="stretch", hide_index=True)

    rotation = sector_rotation_board(ranking_grouped, hierarchy)
    if not rotation.empty:
        st.subheader("行业轮动观察", icon=":material/autorenew:")
        st.caption("基于当前收盘快照的行业相对涨跌、内部上涨广度和活跃规模做复盘定位；红色代表相对强势，绿色代表相对弱势，不构成后续走势判断。")
        rotation_strong = int((rotation["轮动状态"] == "强势扩散").sum())
        rotation_pressure = int((rotation["轮动状态"] == "承压").sum())
        rotation_summary, rotation_chart_col, rotation_table_col = st.columns([0.75, 1.55, 1.7], vertical_alignment="top")
        with rotation_summary:
            with st.container(border=True):
                st.metric("强势扩散", rotation_strong, border=True)
                st.metric("承压行业", rotation_pressure, border=True)
                st.metric("最高轮动热度", f"{int(rotation['轮动热度'].max())}/100", border=True)
                st.caption("热度用于同一份快照内的横向比较。")
        with rotation_chart_col:
            with st.container(border=True):
                rotation_chart_frame = rotation.head(12).sort_values("轮动热度")
                rotation_chart = px.bar(
                    rotation_chart_frame,
                    x="轮动热度",
                    y=hierarchy,
                    orientation="h",
                    color="涨跌幅",
                    color_continuous_scale="RdYlGn_r",
                    color_continuous_midpoint=0,
                    hover_data={"上涨占比": ":.0%", "成交额": ":.3s", "轮动状态": True},
                )
                rotation_chart.update_layout(height=315, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="轮动热度（0–100）", yaxis_title="")
                st.plotly_chart(rotation_chart, width="stretch")
        with rotation_table_col:
            with st.container(border=True):
                rotation_columns = [hierarchy, "轮动热度", "轮动状态", "涨跌幅", "上涨占比", "成交额"]
                table(
                    _ashare_change_style(rotation.head(10)[rotation_columns]),
                    column_config={
                        "轮动热度": st.column_config.ProgressColumn("轮动热度", min_value=0, max_value=100, format="%d"),
                        "涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
                        "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
                        "成交额": st.column_config.NumberColumn("规模", format="compact"),
                    },
                    width="stretch",
                    hide_index=True,
                    height=315,
                )

    stock_rank_columns = [field for field in ("代码", "名称", "涨跌幅", size_field, "行业", "细分行业") if field in stocks.columns]
    stock_rank_config = {
        "涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%.2f%%"),
        size_field: st.column_config.NumberColumn(size_field, format="compact"),
    }
    mover_left, mover_mid, mover_right = st.columns(3, vertical_alignment="top")
    with mover_left:
        with st.container(border=True):
            st.subheader("涨幅居前个股")
            table(_ashare_change_style(stocks.sort_values("涨跌幅", ascending=False).head(12)[stock_rank_columns]), column_config=stock_rank_config, width="stretch", hide_index=True, height=360)
    with mover_mid:
        with st.container(border=True):
            st.subheader("跌幅居前个股")
            table(_ashare_change_style(stocks.sort_values("涨跌幅").head(12)[stock_rank_columns]), column_config=stock_rank_config, width="stretch", hide_index=True, height=360)
    with mover_right:
        with st.container(border=True):
            st.subheader("规模活跃个股")
            table(_ashare_change_style(stocks.sort_values(size_field, ascending=False).head(12)[stock_rank_columns]), column_config=stock_rank_config, width="stretch", hide_index=True, height=360)

    st.subheader(f"{hierarchy}下钻与个股活跃榜")
    drill_options = display_grouped[hierarchy].dropna().astype(str).drop_duplicates().sort_values().tolist()
    query_context = industry_query.strip()
    matched_industries = [item for item in drill_options if query_context and query_context.casefold() in item.casefold()]
    if query_context and matched_industries and state.get(prefix+"terminal_drilldown_context") != query_context:
        state[prefix+"terminal_drilldown"] = matched_industries[0]
        state[prefix+"terminal_drilldown_context"] = query_context
    elif not query_context:
        state[prefix+"terminal_drilldown_context"] = ""
    selected_industry = st.selectbox(f"选择{hierarchy}查看成分股", drill_options, key=prefix+"terminal_drilldown", persist_state="session")
    members = map_stocks.loc[map_stocks[hierarchy].astype(str) == selected_industry].copy()
    member_up = int((members["涨跌幅"] > 0).sum())
    member_avg = float(members["涨跌幅"].mean()) if not members.empty else 0.0
    member_up_ratio = float((members["涨跌幅"] > 0).mean()) if not members.empty else 0.0
    market_avg = float(stocks["涨跌幅"].mean()) if stocks["涨跌幅"].notna().any() else 0.0
    industry_row = display_grouped.loc[display_grouped[hierarchy].astype(str) == selected_industry]
    industry_strength = float(industry_row["行业强度"].iloc[0]) if not industry_row.empty else 0.0
    industry_percentile = float((display_grouped["涨跌幅"] <= member_avg).mean() * 100) if not display_grouped.empty else None
    industry_state = "强势" if member_avg >= market_avg + 1 else "偏强" if member_avg > market_avg else "偏弱" if member_avg > market_avg - 1 else "弱势"
    st.badge(industry_state, icon=":material/account_tree:", color="red" if industry_state in {"强势", "偏强"} else "green")
    drill_metrics = st.columns(4)
    drill_metrics[0].metric("成分股", len(members))
    drill_metrics[1].metric("平均涨跌", f"{member_avg:+.2f}%", f"相对市场 {member_avg - market_avg:+.2f}%", delta_color="inverse")
    drill_metrics[2].metric("上涨占比", f"{member_up_ratio:.0%}", f"上涨 {member_up:,} 家")
    drill_metrics[3].metric("行业强度", f"{industry_strength:.0f}/100", f"市场前 {100 - industry_percentile + 1:.0f}%" if industry_percentile is not None else None)
    component_summary = market_component_extremes(members, size_field)
    if component_summary:
        with st.container(border=True):
            st.caption(f"{selected_industry}成分股状态")
            component_cards = st.columns(3, border=True)
            for card, label, key in zip(component_cards, ("领涨成分", "领跌成分", "规模活跃"), ("leader", "laggard", "active")):
                item = component_summary[key]
                with card:
                    st.metric(label, item["名称"], f"{item['涨跌幅']:+.2f}%", delta_color="inverse")
                    st.caption(f"{item['代码']}｜{size_field} {item['规模'] / 1e8:.2f} 亿")
    columns = [field for field in ("代码", "名称", "涨跌幅", size_field, "行业", "细分行业", "板块") if field in stocks.columns]
    stock_left, stock_right = st.columns([3, 1], vertical_alignment="top")
    with stock_left:
        table(_ashare_change_style(members.sort_values(size_field, ascending=False).head(50)[columns]), width="stretch", hide_index=True)
    with stock_right:
        st.caption("市场宽度分布")
        buckets = pd.cut(stocks["涨跌幅"], [-float("inf"), -7, -3, 0, 3, 7, float("inf")], labels=["<-7%", "-7~-3%", "-3~0%", "0~3%", "3~7%", ">7%"]).value_counts().reindex(["<-7%", "-7~-3%", "-3~0%", "0~3%", "3~7%", ">7%"], fill_value=0).rename_axis("区间").reset_index(name="数量")
        bucket_colors = {
            "<-7%": "#22c55e", "-7~-3%": "#4ade80", "-3~0%": "#86efac",
            "0~3%": "#fca5a5", "3~7%": "#f87171", ">7%": "#dc2626",
        }
        bucket_chart = px.bar(buckets, x="区间", y="数量", color="区间", color_discrete_map=bucket_colors)
        bucket_chart.update_layout(height=310, margin=dict(t=8, l=2, r=2, b=4), showlegend=False)
        st.plotly_chart(bucket_chart, width="stretch")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"已选{hierarchy}：{selected_industry}。可将云图中的行业强弱直接与导入的资金回放对照。")
        if st.button("对照行业资金流向", icon=":material/timeline:", key=prefix+"terminal_open_capital_replay"):
            state[prefix+"research_context"] = {"source": "大盘云图", "industry": selected_industry}
            navigation.open_page("板块资金流向")
            st.rerun()
    if {"代码", "名称"}.issubset(members.columns) and not members.empty:
        member_labels = (members["代码"].astype(str) + " · " + members["名称"].fillna("未命名").astype(str)).tolist()
        with st.container(horizontal=True, vertical_alignment="bottom"):
            selected_member = st.selectbox("从当前行业打开个股研究", member_labels, key=prefix+"terminal_stock_jump")
            if st.button("打开个股详情", icon=":material/open_in_new:", key=prefix+"terminal_open_stock"):
                target_frame=members.assign(个股=members["代码"].astype(str)+" · "+members["名称"].fillna("未命名").astype(str))
                if not open_stock_widget(target_frame,hierarchy,selected_member,navigation,prefix):
                    st.warning("当前股票选择无效。")
                    return
                st.rerun()
    with st.container(border=True):
        st.subheader(f"全{hierarchy}总榜")
        st.caption(f"当前云图显示 {len(display_grouped):,} 个{hierarchy}；总榜显示其中样本不少于 {ranking_minimum} 只的 {len(ranking_grouped):,} 个分类。")
        full_rank = ranking_grouped.sort_values(["行业强度", "成交额"], ascending=[False, False])[rank_columns]
        table(_ashare_change_style(full_rank), column_config=rank_config, width="stretch", hide_index=True, height=520)
    export_left, export_right = st.columns(2)
    with export_left:
        download("导出行业云图数据 CSV", quote_export(display_grouped, data).to_csv(index=False, encoding="utf-8-sig"), "market_terminal_industries.csv", "text/csv")
    with export_right:
        download("导出当前行业成分股 CSV", quote_export(members[columns], data).to_csv(index=False, encoding="utf-8-sig"), f"{selected_industry}_members.csv", "text/csv")

