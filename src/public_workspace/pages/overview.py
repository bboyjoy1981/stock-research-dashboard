"""Original final overview, using explicit public sources and isolated controls."""
from datetime import datetime,timezone
import pandas as pd
import plotly.express as px
import streamlit as st
from ...calculations import (market_close_review,market_overview_radar,market_sector_turnover,
    market_overview_distribution,market_snapshot_trend,market_history_coverage,market_trend_summary,sector_rotation_board)
from ...close_brief import build_close_brief
from ..market_groups import market_group_display_mask,researchable_market_groups
from ..scanner_model import select_market_group_column
from ..detail_model import quote_export,_ashare_change_style
from ..contracts import PublicSnapshot
from ..temperature_model import public_inputs
from ..news_model import decode_news_dataset
from ..close_pool_model import decode_close_pool
from .stock_detail import quote_origin
from .temperature import TemperatureView
from .overview_panels import OverviewPanels
from .cloud_components import render_sector_lens


def index_help(quote):
    change=pd.to_numeric(pd.Series([quote.get('涨跌')]),errors='coerce').iloc[0]
    return str(quote.get('来源','来源未提供'))+'｜源日期 '+str(quote.get('交易日期','未提供'))+'｜源时间 '+str(quote.get('源时间','未提供'))+'｜涨跌点数 '+(f'{change:+.2f}' if pd.notna(change) else '未提供')


def render(snapshot,capabilities,navigation):
    snapshot=PublicSnapshot(snapshot.stocks,snapshot.indices,dict(snapshot.metadata),dict(snapshot.optional))
    prior=snapshot.optional.get('history')
    history=prior.frame.copy() if prior is not None else pd.DataFrame()
    history=pd.concat([history,snapshot.stocks.assign(快照日期=snapshot.metadata['date'],快照来源=snapshot.metadata['source'])],ignore_index=True)
    data=dict(stocks=snapshot.stocks,indices=snapshot.indices,index_snapshot=snapshot.indices,
        import_date=snapshot.metadata['date'],stock_quote_source='imported',public_source=snapshot.metadata['source'],market_history=history)
    data.update(public_inputs(snapshot.optional.get('temperature')))
    pool=snapshot.optional.get('close_limits')
    if pool is not None:
        data['close_limit_snapshot']=decode_close_pool(pool)
    news=snapshot.optional.get('news')
    if news is not None:
        try: data['public_news_state']=decode_news_dataset(news,datetime.now(timezone.utc))
        except (ValueError,TypeError,KeyError): data['public_news_state']=None
    render_frame(data,capabilities,navigation,navigation.namespace+'_')

def render_frame(data,capabilities,navigation,prefix="",owner_temperature_ui=None):
    """Finished, first-screen market entry: status → industry scan → stock research."""

    state=navigation.state
    panels=OverviewPanels(data,capabilities,navigation,prefix)
    def render_temperature(data,container):
        if navigation.namespace=='owner' and owner_temperature_ui is not None:
            return owner_temperature_ui(data,headline_container=container)
        return TemperatureView(data,capabilities,navigation,prefix).render_market_temperature(data,container)
    def _focus_overview_industry(target,field):
        industry=state.get(prefix+'overview_primary_industry')
        frame=data['stocks']
        if field not in frame or industry not in set(frame[field].dropna().astype(str)): return
        state[prefix+'research_context']=dict(source='市场总览 · 行业排行',industry=industry,field=field)
        if target=='members':
            state[prefix+'overview_stock_scope']=industry
            state[prefix+'overview_workspace']='行情榜单'
        elif target=='cloud':
            panels.focus_sector(field,industry)

    stocks = data.get("stocks", pd.DataFrame()).copy()
    indices = data.get("indices", pd.DataFrame()).copy()
    stocks = stocks.loc[:, ~stocks.columns.duplicated()].copy()
    if stocks.empty or "涨跌幅" not in stocks.columns:
        st.title("市场总览")
        st.warning("当前没有可用于市场研究的行情快照，请在数据导入中保存包含涨跌幅的全市场文件。")
        return
    for field in ("涨跌幅", "成交额", "价格", "流通市值", "总市值"):
        if field in stocks.columns:
            stocks[field] = pd.to_numeric(stocks[field], errors="coerce")
    # Missing returns are unknown quotes, not unchanged stocks.
    valid_stocks = stocks.loc[stocks["涨跌幅"].notna()].copy()
    if valid_stocks.empty:
        st.subheader("市场总览 · 收盘研究看板", icon=":material/dashboard:")
        st.warning("快照中没有有效涨跌幅，无法判断市场强弱；请导入含行情字段的收盘文件。")
        return
    amount_available = "成交额" in stocks and stocks["成交额"].gt(0).any()
    size_field = next((field for field in ("成交额", "流通市值", "总市值") if field in stocks.columns and stocks[field].gt(0).any()), None)
    industry_field = select_market_group_column(stocks)
    ambiguous_child=(industry_field=="细分行业" and "行业" in stocks and stocks.groupby("细分行业")["行业"].nunique().gt(1).any())
    if ambiguous_child: industry_field="行业"
    if industry_field:
        stocks[industry_field] = stocks[industry_field].fillna("未分类").astype(str).replace("", "未分类")
        aggregation = {"涨跌幅": ("涨跌幅", "mean"), "股票数": ("涨跌幅", "size")}
        sector_frame = valid_stocks.groupby(industry_field, dropna=False).agg(**aggregation).reset_index()
        sector_frame["上涨占比"] = valid_stocks.groupby(industry_field)["涨跌幅"].apply(lambda values: float((values > 0).mean())).values
        sector_frame = sector_frame.merge(market_sector_turnover(valid_stocks, industry_field), on=industry_field, how="left")
    else:
        sector_frame = pd.DataFrame(columns=["行业", "涨跌幅", "股票数", "成交额", "上涨占比"])
        industry_field = "行业"
    if "成交额" not in sector_frame.columns:
        sector_frame["成交额"] = float("nan")
    visible_sector_mask = market_group_display_mask(sector_frame, industry_field)
    if bool(visible_sector_mask.any()):
        sector_frame = sector_frame.loc[visible_sector_mask].copy()
    classification_label = "市场分类" if industry_field == "板块" else industry_field
    sector_rank_frame = researchable_market_groups(sector_frame, minimum_samples=3)
    if sector_rank_frame.empty:
        sector_rank_frame = sector_frame.copy()

    up = int((stocks["涨跌幅"] > 0).sum())
    down = int((stocks["涨跌幅"] < 0).sum())
    flat = int(stocks["涨跌幅"].eq(0).sum())
    total = max(len(valid_stocks), 1)
    strength = max(0, min(100, round(50 + (up - down) / total * 50)))
    market_state = "普涨" if up > down * 1.5 else "普跌" if down > up * 1.5 else "结构分化"
    close_review = market_close_review(stocks, sector_rank_frame, industry_field)
    market_radar = market_overview_radar(stocks, sector_rank_frame, industry_field)

    st.subheader("市场总览 · 收盘研究看板", icon=":material/dashboard:")
    st.caption(f"{quote_origin(data)} · 地图定位行业 → 活跃股筛选 → 个股同类比较。")
    if ambiguous_child:
        st.caption("存在同名细分行业的多个父级；本页排行按上级行业比较，细分范围请在云图按父级核对，不混并同名子行业。")
    st.subheader("收盘市场脉冲", icon=":material/monitoring:")

    pulse_amount, pulse_state, pulse_temperature = st.columns([1.1, .9, 2], vertical_alignment='top')
    with pulse_amount:
        panels.render_market_activity(data)
    with pulse_state:
        with st.container(key=prefix+'pulse_market_state', border=True):
            st.metric("市场状态", close_review["市场状态"], help=f"上涨占比 {market_radar['上涨占比']:.0%}" if market_radar["上涨占比"] is not None else "上涨占比未知")
            st.caption('当前个股涨跌广度 · 不等同综合市场温度')

    render_temperature(data,pulse_temperature)
    st.subheader('核心指数 · 收盘行情', icon=':material/show_chart:')
    index_snapshot = data.get('index_snapshot', pd.DataFrame())
    with st.container(horizontal=True):
        for index_name in ['上证指数', '深证成指', '创业板指', '科创50', '沪深300']:
            found = index_snapshot.loc[index_snapshot['名称'].eq(index_name)] if not index_snapshot.empty else pd.DataFrame()
            if found.empty:
                st.metric(index_name, '待接入', border=True, help='当前复盘日期暂无真实指数快照。')
            else:
                quote = found.iloc[0]
                st.metric(index_name, f"{quote['价格']:,.2f}", f"{quote['涨跌幅']:+.2f}%", delta_color='inverse', border=True,
                          help=index_help(quote))
    if index_snapshot.empty:
        st.info('未导入真实指数行情：指数收盘点位、涨跌幅、成交量/额及走势暂缺。下方市场统计来自当前个股快照，不代表指数表现。')
    else:
        dates=sorted(set(index_snapshot["交易日期"].dropna().astype(str))) if "交易日期" in index_snapshot else []
        sources=sorted(set(index_snapshot["来源"].dropna().astype(str))) if "来源" in index_snapshot else []
        st.caption("指数交易日："+"、".join(dates or ["未提供"])+"｜指数来源："+"、".join(sources or ["未提供"])+"；与个股来源日期分别列示，非实时。指数分时及成交量/额尚未接入。")
    with st.container(horizontal=True):
        st.metric("上涨 / 下跌", f"{up:,} / {down:,}", border=True)
        st.metric("平均涨跌", f"{close_review['平均涨跌']:+.2f}%" if close_review["平均涨跌"] is not None else "—", border=True,
                  help=f"当前 {len(valid_stocks):,} 只有效个股涨跌幅的算术平均，每只股票权重相同，包含平盘、排除缺失值；不是指数涨跌幅。")

        panels.render_close_limit_metric(stocks, data.get('import_date'), data.get('close_limit_snapshot'))
    st.caption(f"领涨{classification_label}：{market_radar['领涨行业'] or '—'} · 领跌：{market_radar['领跌行业'] or '—'} · 规模活跃：{market_radar['活跃行业'] or '待导入成交额'} · 平盘 {flat:,} 家 · 缺失涨跌 {len(stocks) - len(valid_stocks):,} 家")

    panels.render_news_preview(data.get('import_date'))
    overview_tabs = st.tabs(['市场地图', '行业研究', '行情榜单', '收盘报告'], key=prefix+'overview_workspace', on_change='rerun')
    with overview_tabs[3]:

        panels.render_closing_report(data, sector_rank_frame, industry_field)
    with overview_tabs[0]:
        primary_left, primary_right = st.columns([2.5, 1], vertical_alignment="top")
    with primary_left:
        st.subheader("全市场研究视窗", icon=":material/account_tree:")
        visual_mode = st.segmented_control("市场视角", ["市场云图", "行业排行"],
                                           default="市场云图", key=prefix+"overview_visual_mode") or "市场云图"
        if visual_mode == "市场云图":

            with st.container(border=True):
                panels.render_overview_map(stocks, industry_field, size_field)
        ranking_surface = st.expander(f"{classification_label}强弱与活跃度", expanded=False) if visual_mode == "市场云图" else st.container()
    with ranking_surface:
        ranking_modes = ["领涨", "领跌"] + (["成交活跃"] if amount_available else [])
        ranking_mode = st.segmented_control(
            "板块排行口径", ranking_modes, default="领涨", key=prefix+"overview_sector_rank_mode",
        ) or "领涨"
        rank_field = "成交额" if ranking_mode == "成交活跃" else "涨跌幅"
        rank_ascending = ranking_mode == "领跌"
        ranked_sectors = sector_rank_frame.dropna(subset=[rank_field]).sort_values(rank_field, ascending=rank_ascending)
        sector_left, sector_right = st.container(), st.expander("行业排行明细", expanded=False)
        sector_config = {
            "涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
            "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
            "成交额": st.column_config.NumberColumn("规模", format="compact"),
            "股票数": st.column_config.NumberColumn("样本数", format="%,d"),
        }
        with sector_left:
            with st.container(border=True):
                if not sector_frame.empty:
                    leaders = ranked_sectors.head(15).sort_values(rank_field, ascending=not rank_ascending)
                    leader_chart = px.bar(leaders, x=rank_field, y=industry_field, orientation="h", color="涨跌幅", color_continuous_scale="RdYlGn_r", color_continuous_midpoint=0)
                    leader_chart.update_layout(height=340, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="成交额（元）" if ranking_mode == "成交活跃" else "平均涨跌幅（%）", yaxis_title="")
                    st.plotly_chart(leader_chart, width="stretch")
        with sector_right:
            with st.container(border=True):
                st.markdown(f"**{ranking_mode}{classification_label}**")
                rank_columns = [field for field in (industry_field, "涨跌幅", "上涨占比", "成交额", "股票数") if field in ranked_sectors]
                panels.table(_ashare_change_style(ranked_sectors.head(12)[rank_columns]), column_config=sector_config, width="stretch", hide_index=True, height=420)
        if not ranked_sectors.empty:
            focus_options = ranked_sectors[industry_field].dropna().astype(str).drop_duplicates().tolist()
            if state.get(prefix+"overview_primary_industry") not in focus_options:
                state[prefix+"overview_primary_industry"] = focus_options[0]
            with st.container(horizontal=True, vertical_alignment="bottom"):
                st.selectbox("选择行业继续研究", focus_options, key=prefix+"overview_primary_industry")
                st.button("看成分股", icon=":material/list_alt:", key=prefix+"overview_primary_members",
                          on_click=_focus_overview_industry, args=("members", industry_field))
                st.button("定位云图", icon=":material/account_tree:", key=prefix+"overview_primary_cloud",
                          on_click=_focus_overview_industry, args=("cloud", industry_field))
    with primary_right:
        with st.container(border=True):
            st.subheader("涨跌结构", icon=":material/bar_chart:")
            structure_frame = market_overview_distribution(stocks)
            structure_colors = {
                "<-5%": "#22c55e", "-5%~-2%": "#4ade80", "-2%~0%": "#86efac", "0%": "#64748b",
                "0%~2%": "#fca5a5", "2%~5%": "#f87171", ">5%": "#dc2626",
            }
            structure_chart = px.bar(structure_frame, x="区间", y="家数", color="区间", color_discrete_map=structure_colors)
            structure_chart.update_layout(height=245, margin=dict(t=6, l=0, r=0, b=0), showlegend=False, xaxis_title="", yaxis_title="家数")
            st.plotly_chart(structure_chart, width="stretch")
            st.caption(f"上涨 {up:,}｜平盘 {flat:,}｜下跌 {down:,}")
        with st.container(border=True):
            st.subheader("行业速览", icon=":material/leaderboard:")
            glance = sector_rank_frame.dropna(subset=["涨跌幅"]).sort_values("涨跌幅", ascending=False)
            glance_fields = [field for field in (industry_field, "涨跌幅", "股票数") if field in glance]
            panels.table(_ashare_change_style(glance.head(6)[glance_fields]), hide_index=True,
                         column_config={"涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%+.2f%%")},
                         width="stretch", height=245)

    with overview_tabs[1]:
        render_sector_lens(stocks, industry_field, data, prefix+'overview_lens',capabilities,navigation,session_prefix=prefix)
    with overview_tabs[2]:

        panels.render_limit_lists(stocks, data.get('import_date'), data.get('close_limit_snapshot'))
        st.subheader("活跃个股" if amount_available else f"{size_field}靠前个股" if size_field else "涨幅靠前个股", icon=":material/bolt:")
    stock_columns = list(dict.fromkeys(field for field in ("代码", "名称", "价格", "涨跌幅", "成交额", size_field, industry_field, "板块") if field in stocks.columns))
    activity_source = valid_stocks if not valid_stocks.empty else stocks
    with overview_tabs[2]:
        activity_controls = st.columns([1.4, 1, 0.6], vertical_alignment="bottom")
    activity_modes = ["领涨个股", "领跌个股"]
    if size_field:
        activity_modes.insert(0, "成交活跃" if amount_available else f"{size_field}靠前")
    with activity_controls[0]:
        activity_mode = st.segmented_control("个股排行口径", activity_modes, default=activity_modes[0], key=prefix+"overview_stock_rank_mode") or activity_modes[0]
    with activity_controls[1]:
        stock_scopes = ["全市场", *sorted(activity_source[industry_field].dropna().astype(str).unique().tolist())]
        stock_scope = st.selectbox("个股范围", stock_scopes, key=prefix+"overview_stock_scope")
    with activity_controls[2]:
        stock_limit = st.selectbox("榜单数量", [15, 30, 60], index=1, key=prefix+"overview_stock_limit")
    if stock_scope not in stock_scopes or activity_mode not in activity_modes or type(stock_limit) is not int or stock_limit not in (15,30,60):
        st.warning("榜单筛选选项无效。")
        return
    if stock_scope != "全市场":
        activity_source = activity_source.loc[activity_source[industry_field].astype(str).eq(stock_scope)]
    activity_sort_field = "涨跌幅" if activity_mode in {"领涨个股", "领跌个股"} else size_field
    activity = activity_source.dropna(subset=[activity_sort_field]).sort_values(activity_sort_field, ascending=activity_mode == "领跌个股").head(stock_limit)
    with overview_tabs[2]:
        table_left, table_right = st.columns([2.2, 1], vertical_alignment="top")
    with table_left:
        panels.table(_ashare_change_style(activity[stock_columns]), column_config={"涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%.2f%%"), "成交额": st.column_config.NumberColumn("成交额", format="compact"), "价格": st.column_config.NumberColumn("价格", format="%.2f")}, width="stretch", hide_index=True, height=440)
    with table_right:
        if not activity.empty and {"代码", "名称"}.issubset(activity.columns):
            options = (activity["代码"].astype(str) + " · " + activity["名称"].fillna("未命名").astype(str)).tolist()
            selected = st.selectbox("研究一只活跃股", options, key=prefix+"summary_stock_jump")
            if st.button("打开研究卡", icon=":material/open_in_new:", key=prefix+"summary_open_stock"):
                if selected not in options or not panels.open_stock(selected.split(" · ",1)[0]):
                    st.warning("股票选择无效。")
                    return
                st.rerun()
        else:
            st.caption("当前范围没有满足排行口径的个股，请调整筛选。")
        panels.download(
            "导出当前个股榜单", quote_export(activity[stock_columns], data).assign(排行口径=activity_mode, 筛选范围=stock_scope).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{stock_scope}_{activity_mode}.csv", mime="text/csv",
            icon=":material/download:", key=prefix+"overview_stock_rank_export",
        )
        st.caption("建议路径：先用云图定位强弱行业，再对行业内活跃股做同类比较。")

    with overview_tabs[3]:
        panels.render_market_snapshot_comparison(data)
    close_trend = market_snapshot_trend(
        data.get("market_history", pd.DataFrame()),
        through_date=data.get("import_date") if data.get("stock_quote_source") == "imported" else None,
    )
    if not close_trend.empty:
        history_coverage = market_history_coverage(close_trend)
        with overview_tabs[3].expander("多日市场回放", expanded=False, icon=":material/timeline:"):
            st.caption(f"每个交易日仅采用该日最新导入快照，避免同日重复上传造成成交额和家数重复累计。当前覆盖 {history_coverage['交易日数']} 日：{history_coverage['起始日']} 至 {history_coverage['截至日']}。")
            review_controls = st.columns([1, 1.5], vertical_alignment="bottom")
            with review_controls[0]:
                review_period = st.selectbox("回放范围", ["最近 5 日", "最近 10 日", "全部",], key=prefix+"overview_history_period")
            with review_controls[1]:
                review_view = st.segmented_control("回放指标", ["上涨广度", "平均涨跌", "成交额"], default="上涨广度", key=prefix+"overview_history_metric")
            period_count = {"最近 5 日": 5, "最近 10 日": 10, "全部": len(close_trend)}[review_period]
            review_trend = close_trend.tail(period_count).copy()
            latest_history = review_trend.iloc[-1]
            with st.container(horizontal=True):
                st.metric("最新上涨占比", f"{latest_history['上涨占比']:.0%}", border=True)
                st.metric("最新平均涨跌", f"{latest_history['平均涨跌']:+.2f}%", border=True)
            review_column = {"上涨广度": "上涨占比", "平均涨跌": "平均涨跌", "成交额": "成交额"}[review_view]
            if review_view == "成交额" and not review_trend["成交额"].notna().any():
                st.info("所选日期没有可用成交额，不能绘制成交趋势。")
            elif len(review_trend) >= 2:
                st.line_chart(review_trend.set_index("交易日")[review_column], height=220)
            else:
                st.info("目前仅保存一个交易日，待下一交易日导入后显示连续趋势。")
            trend_summary = market_trend_summary(review_trend)
            if trend_summary["最高广度"] is not None:
                average_amount = f"{trend_summary['平均成交额'] / 1e8:.2f} 亿" if trend_summary["平均成交额"] is not None else "未提供"
                st.caption(f"所选区间上涨广度 {trend_summary['最低广度']:.0%}–{trend_summary['最高广度']:.0%}｜日均成交额 {average_amount}。仅比较已保存日期，不填补缺失交易日。")
            partial_amount_days = review_trend.loc[review_trend["成交额有效数"] < review_trend["样本数"], "交易日"]
            if not partial_amount_days.empty:
                st.caption(f"成交额数据不完整：{len(partial_amount_days)} 个交易日存在缺失值，相关金额仅汇总已提供的股票。")
            with st.expander("查看回放数据明细", expanded=False):
                panels.table(review_trend.sort_values("交易日", ascending=False), width="stretch", hide_index=True)
                panels.download(
                    "导出当前回放 CSV",
                    review_trend.to_csv(index=False).encode("utf-8-sig"),
                    file_name="市场多日回放.csv",
                    mime="text/csv",
                    icon=":material/download:",
                    key=prefix+"overview_history_download",
                )
            if st.button("在大盘云图查看详细复盘", icon=":material/account_tree:", key=prefix+"overview_history_to_terminal"):
                navigation.open_page("大盘云图")
                st.rerun()
    if not sector_rank_frame.empty:
        route_frame = sector_rank_frame.copy()
        for numeric_field in ("涨跌幅", "上涨占比", "成交额", "股票数"):
            if numeric_field in route_frame.columns:
                route_frame[numeric_field] = pd.to_numeric(route_frame[numeric_field], errors="coerce")
        route_frame = route_frame.dropna(subset=[industry_field])
        if route_frame.empty:
            route_frame = sector_rank_frame.copy()
            route_frame["涨跌幅"] = pd.to_numeric(route_frame.get("涨跌幅"), errors="coerce").fillna(0.0)
        observation_rows = []
        observation_specs = [
            ("强度领先", route_frame.sort_values(["涨跌幅", "成交额"], ascending=[False, False])),
            ("上涨广度", route_frame.sort_values(["上涨占比", "股票数"], ascending=[False, False]) if "上涨占比" in route_frame else route_frame),
            *(([("成交活跃", route_frame.sort_values("成交额", ascending=False))] if amount_available else [])),
            ("相对落后", route_frame.sort_values(["涨跌幅", "成交额"], ascending=[True, False])),
        ]
        seen_observations = set()
        for angle, ordered in observation_specs:
            candidate = next((row for _, row in ordered.iterrows() if str(row[industry_field]) not in seen_observations), None)
            if candidate is None:
                continue
            seen_observations.add(str(candidate[industry_field]))
            item = candidate.to_dict()
            item["研究角度"] = angle
            item["相对市场"] = float(candidate["涨跌幅"] - close_review["平均涨跌"]) if close_review["平均涨跌"] is not None else None
            observation_rows.append(item)
        observation_queue = pd.DataFrame(observation_rows)
        with overview_tabs[1].expander("次日研究路径 · 方向与代表个股", expanded=False, icon=":material/route:"):
            st.subheader("次日研究路径", icon=":material/route:")
            st.caption("先读市场情绪，再核对强度、上涨广度和相对落后方向；仅在有成交额时加入成交活跃方向。清单不构成次日买卖信号。")
            if not observation_queue.empty:
                display_columns = [field for field in ("研究角度", industry_field, "涨跌幅", "上涨占比", "成交额", "股票数", "相对市场") if field in observation_queue.columns]
                panels.table(
                    _ashare_change_style(observation_queue[display_columns]),
                    column_config={
                        "涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%+.2f%%"),
                        "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
                        "成交额": st.column_config.NumberColumn("成交额", format="compact"),
                        "股票数": st.column_config.NumberColumn("样本数", format="%,d"),
                        "相对市场": st.column_config.NumberColumn("相对市场", format="%+.2f%%"),
                    },
                    width="stretch",
                    hide_index=True,
                )
                panels.download(
                    "导出观察清单 CSV",
                    observation_queue.to_csv(index=False).encode("utf-8-sig"),
                    file_name="次日研究观察清单.csv",
                    mime="text/csv",
                    icon=":material/download:",
                    key=prefix+"overview_route_download",
                )
            focus_labels = [f"{row['研究角度']} · {row[industry_field]}" for _, row in observation_queue.iterrows()]
            if not focus_labels:
                focus_labels = [str(value) for value in route_frame[industry_field].astype(str).tolist()]
                observation_queue = route_frame.copy()
                observation_queue["研究角度"] = "行业观察"
            with st.container(horizontal=True, vertical_alignment="bottom"):
                selected_focus = st.selectbox("选择待核对方向", focus_labels, key=prefix+"overview_route_focus")
            selected_index = focus_labels.index(selected_focus)
            route_sector = observation_queue.iloc[selected_index]
            route_industry = str(route_sector[industry_field])
            with st.container(horizontal=True):
                st.metric("市场环境", close_review["市场状态"], border=True)
                st.metric(f"{route_sector['研究角度']} · {classification_label}", route_industry, f"{route_sector['涨跌幅']:+.2f}%", delta_color="inverse", border=True)
                st.metric("行业上涨占比", f"{route_sector['上涨占比']:.0%}" if pd.notna(route_sector.get("上涨占比")) else "—", border=True)
                st.metric("行业成交额", f"{route_sector['成交额'] / 1e8:.2f} 亿" if pd.notna(route_sector.get("成交额")) else "—", border=True)
            peers = stocks.loc[stocks[industry_field].astype(str).eq(route_industry)].copy()
            if not peers.empty:
                peers["涨跌幅"] = pd.to_numeric(peers["涨跌幅"], errors="coerce")
                peers = peers.dropna(subset=["涨跌幅"])
                if "成交额" not in peers:
                    peers["成交额"] = float("nan")
                peers["成交额"] = pd.to_numeric(peers["成交额"], errors="coerce")
                peer_rows = []
                peer_orders = [("涨幅靠前", peers.sort_values(["涨跌幅", "成交额"], ascending=[False, False]).head(5))]
                if peers["成交额"].notna().any():
                    peer_orders.append(("成交活跃", peers.dropna(subset=["成交额"]).sort_values(["成交额", "涨跌幅"], ascending=[False, False]).head(5)))
                for angle, ordered in peer_orders:
                    selected_peers = ordered.copy()
                    selected_peers["观察角度"] = angle
                    peer_rows.append(selected_peers)
                representative_stocks = pd.concat(peer_rows, ignore_index=True)
                dedupe_key = "代码" if "代码" in representative_stocks else "名称" if "名称" in representative_stocks else None
                if dedupe_key:
                    representative_stocks = representative_stocks.drop_duplicates(dedupe_key, keep="first")
                st.subheader(f"{route_industry} · 代表个股", icon=":material/leaderboard:")
                st.caption(f"方向内共 {len(peers):,} 只有效行情样本；按涨幅排序" + ("，并核对成交活跃个股。" if peers["成交额"].notna().any() else "；成交额未提供，未生成活跃排行。"))
                peer_columns = [field for field in ("观察角度", "代码", "名称", "涨跌幅", "成交额") if field in representative_stocks]
                panels.table(
                    _ashare_change_style(representative_stocks[peer_columns]),
                    column_config={
                        "涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%+.2f%%"),
                        "成交额": st.column_config.NumberColumn("成交额", format="compact"),
                    },
                    width="stretch",
                    hide_index=True,
                )
                if "名称" in representative_stocks:
                    stock_labels = []
                    stock_lookup = {}
                    for _, peer in representative_stocks.iterrows():
                        code = str(peer.get("代码", "")).replace(".0", "")
                        name = str(peer.get("名称", "未命名"))
                        label = f"{code} · {name}" if code else name
                        stock_labels.append(label)
                        stock_lookup[label] = code or name
                    with st.container(horizontal=True, vertical_alignment="bottom"):
                        selected_peer = st.selectbox("打开代表个股", stock_labels, key=prefix+"overview_route_stock")
                        if st.button("查看该股详情", icon=":material/open_in_new:", key=prefix+"overview_route_open_stock"):
                            if selected_peer not in stock_lookup or not panels.open_stock(stock_lookup[selected_peer]):
                                st.warning("股票选择无效。")
                                return
                            st.rerun()
            with st.container(horizontal=True):
                if st.button("在云图验证行业结构", icon=":material/account_tree:", key=prefix+"overview_route_terminal"):
                    panels.focus_sector(industry_field,route_industry)
                    st.rerun()
                if st.button("查看同业个股", icon=":material/query_stats:", key=prefix+"overview_route_detail"):
                    state[prefix+"research_context"] = {"source": "市场总览 · 次日研究路径", "industry": route_industry,"field":industry_field}
                    state[prefix+"stock_detail_query"] = ""
                    navigation.open_page("个股详情")
                    st.rerun()
                if st.button("对照资金流向", icon=":material/timeline:", key=prefix+"overview_route_replay"):
                    state[prefix+"research_context"] = {"source": "市场总览 · 次日研究路径", "industry": route_industry,"field":industry_field}
                    navigation.open_page("板块资金流向")
                    st.rerun()
    with overview_tabs[1]:
        st.caption('行业重点排序与活跃度观察：基于当前收盘快照，不预测次日走势，也不等同于多日资金轮动。')
        if not sector_frame.empty:
            research_frame = researchable_market_groups(sector_frame, minimum_samples=3)
            if research_frame.empty:
                research_frame = sector_frame.copy()
            research_frame["研究优先级"] = (
                research_frame["涨跌幅"].rank(pct=True).fillna(0) * 45
                + research_frame["上涨占比"].rank(pct=True).fillna(0) * 30
                + research_frame["成交额"].rank(pct=True).fillna(0) * 25
            ).round(0)
            research_focus = research_frame.sort_values(["研究优先级", "成交额"], ascending=[False, False]).head(5).copy()
            research_focus["研究提示"] = research_focus.apply(
                lambda row: f"平均涨跌 {row['涨跌幅']:+.2f}%｜上涨占比 {row['上涨占比']:.0%}", axis=1
            )
            with st.container(border=True):
                st.subheader(f"优先研究{classification_label}", icon=":material/travel_explore:")
                st.caption(f"按{classification_label}相对涨跌、上涨广度" + ("和成交活跃度" if amount_available else "（成交额缺失，未计入活跃度）") + "合成排序。默认剔除样本不足 3 只的分类；不代表买卖建议。")
                focus_config = {
                    "研究优先级": st.column_config.ProgressColumn("研究优先级", min_value=0, max_value=100, format="%d 分"),
                    "涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
                    "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
                    "成交额": st.column_config.NumberColumn("规模", format="compact"),
                }
                panels.table(_ashare_change_style(research_focus[[industry_field, "研究优先级", "涨跌幅", "上涨占比", "成交额", "研究提示"]]), column_config=focus_config, width="stretch", hide_index=True)
        if not sector_frame.empty:
            rotation = sector_rotation_board(sector_rank_frame, industry_field) if amount_available else pd.DataFrame()
            if not rotation.empty:
                st.subheader(f"{classification_label}轮动观察", icon=":material/autorenew:")
                st.caption("把相对涨跌、行业内上涨广度和导入快照中的活跃规模合并为收盘后的研究排序；用于复盘定位，不预测后续走势。")
                rotation_left, rotation_right = st.columns([1.15, 1], vertical_alignment="top")
                with rotation_left:
                    with st.container(border=True):
                        heat_frame = rotation.head(12).sort_values("轮动热度")
                        heat_chart = px.bar(
                            heat_frame,
                            x="轮动热度",
                            y=industry_field,
                            orientation="h",
                            color="涨跌幅",
                            color_continuous_scale="RdYlGn_r",
                            color_continuous_midpoint=0,
                            hover_data={"上涨占比": ":.0%", "成交额": ":.3s", "轮动状态": True},
                        )
                        heat_chart.update_layout(height=360, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="轮动热度（0–100）", yaxis_title="")
                        st.plotly_chart(heat_chart, width="stretch")
                with rotation_right:
                    with st.container(border=True):
                        st.markdown("**观察清单**")
                        rotation_table = rotation.head(10)[[industry_field, "轮动热度", "轮动状态", "涨跌幅", "上涨占比", "成交额"]]
                        panels.table(
                            _ashare_change_style(rotation_table),
                            column_config={
                                "轮动热度": st.column_config.ProgressColumn("轮动热度", min_value=0, max_value=100, format="%d"),
                                "涨跌幅": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
                                "上涨占比": st.column_config.NumberColumn("上涨占比", format="percent"),
                                "成交额": st.column_config.NumberColumn("规模", format="compact"),
                            },
                            width="stretch",
                            hide_index=True,
                            height=360,
                        )
        if not sector_frame.empty:
            industry_options = sector_frame[industry_field].dropna().astype(str).sort_values().tolist()
            with st.container(horizontal=True, vertical_alignment="bottom"):
                selected_industry = st.selectbox(f"在云图定位{classification_label}", industry_options, key=prefix+"summary_industry_jump")
                if st.button("带筛选进入大盘云图", icon=":material/account_tree:", key=prefix+"summary_open_filtered_terminal"):
                    panels.focus_sector(industry_field,selected_industry)
                    st.rerun()

    with overview_tabs[3].expander("导出当前市场快照", expanded=False):

        brief = build_close_brief(stocks, date=data.get("import_date"), origin=quote_origin(data),
                                  sectors=sector_rank_frame, sector_field=industry_field)
        panels.download("导出收盘复盘简报", brief.encode("utf-8-sig"), "market_close_review.txt",
                           "text/plain", key=prefix+"overview_close_brief_export")
        panels.download("导出全市场快照 CSV", quote_export(stocks, data).to_csv(index=False).encode("utf-8-sig"), "market_snapshot.csv", "text/csv")
        if not sector_frame.empty:
            panels.download("导出行业统计 CSV", quote_export(sector_frame, data).to_csv(index=False).encode("utf-8-sig"), "market_industries.csv", "text/csv")

