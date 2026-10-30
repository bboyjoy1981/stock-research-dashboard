"""Original readonly capital charts and replay panels, with injected public data."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from ..capital_model import (
    capital_replay_segments, capital_replay_readiness, filter_capital_replay_by_date,
    capital_replay_snapshot_map, capital_replay_industry_track, capital_replay_flow_changes,
)
from ..components import public_table
from ..scanner_model import select_market_group_column
from ..market_groups import market_group_display_mask,researchable_market_groups

CAPITAL_TABLE_FIELDS=('时间','行业','净流入额','涨跌幅','成交额','领涨股','样本数','数据来源','主力净流入占比',
    '首时点净流入','末时点净流入','净流入变化')


def render(snapshot,capabilities,navigation):
    prefix=navigation.namespace+'_'
    state=navigation.state
    st.title("板块资金流向",icon=":material/timeline:")
    st.caption(f"个股快照：{snapshot.metadata['date']}｜{snapshot.metadata['source']}")
    with st.container(horizontal=True):
        st.button("返回市场总览",key=prefix+"replay_to_overview",on_click=navigation.open_page,args=("市场总览",))
        st.button("查看大盘云图",key=prefix+"replay_to_terminal",on_click=navigation.open_page,args=("大盘云图",))
    dataset=snapshot.optional.get('capital_replay')
    if dataset is None or dataset.frame.empty:
        st.warning("资金回放来源尚未发布；个股成交额不能替代资金净流入，不生成资金曲线。")
        render_research_links(snapshot.stocks,navigation,prefix)
        render_close_reference(snapshot.stocks,capabilities)
        return
    replay=dataset.frame
    st.caption(f"资金来源：{dataset.metadata['source']}｜来源日期：{dataset.metadata['date']}；只读已发布快照，非实时采集。")
    dates=sorted(replay['时间'].str[:10].unique())
    key=prefix+'capital_replay_live_date'
    from ..capital_model import follow_latest_replay_date
    follow_latest_replay_date(state,key,dates)
    selected=st.selectbox("走势交易日",dates,key=key)
    if selected not in dates:
        st.warning("资金日期无效。")
        return
    day=filter_capital_replay_by_date(replay,selected)
    st.subheader("回放数据完整度",icon=":material/fact_check:")
    render_readiness(replay,selected)
    render_flow_charts(day,state,prefix)
    render_research_links(snapshot.stocks,navigation,prefix)
    render_detail(replay,capabilities,state,prefix)
    render_close_reference(snapshot.stocks,capabilities)


def render_readiness(replay, selected_date=None, track_label='板块资金轨迹'):
    times=sorted(replay.get('时间',pd.Series(dtype=str)).dropna().astype(str).loc[lambda v:v.str.strip().ne('')].unique())
    dates=sorted({value[:10] for value in times if len(value)>=10})
    day=filter_capital_replay_by_date(replay,selected_date) if selected_date else replay
    segments=capital_replay_segments(day)
    readiness=capital_replay_readiness(segments[-1][1] if segments else day)
    with st.container(horizontal=True):
        st.metric("已导入回放日期", f"{len(dates):,}", border=True)
        st.metric("当前分时快照", f"{len(times):,}", border=True)
        st.metric(track_label, f"{replay['行业'].nunique():,}" if "行业" in replay else "0", border=True)
        st.metric("复盘状态", "可回放" if times else "等待快照", border=True)
    with st.container(horizontal=True):
        st.metric("所选交易日可用时点", readiness["时点数"], border=True)
        st.metric("可跟踪行业", readiness["行业数"], border=True)
        st.metric("完整轨迹行业", readiness["完整轨迹行业"], border=True)
        st.metric("完整轨迹覆盖", f"{readiness['完整轨迹占比']:.0%}", border=True)
    if readiness["时点数"] <= 1:
        st.caption("当前数据适合查看收盘资金偏好与行业排行；同一交易日至少导入两个时点后，才会产生行业资金变化榜和全天轨迹。")
    elif readiness["完整轨迹占比"] < 0.7:
        st.caption("已有分时回放基础，但部分行业缺少时点。补齐同一批行业的多时点数据后，行业变化排名会更可靠。")
    else:
        st.caption("当前行业轨迹覆盖较完整，可用于查看当天不同时间点的资金偏好演变。")


def render_close_reference(stocks,capabilities):
    def table(frame,**kwargs):
        return public_table(frame,('行业','细分行业','板块','平均涨跌','成交额','股票数'),capabilities,**kwargs)
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
                    table(
                        close_view.sort_values("成交额", ascending=False).head(20),
                        column_config={
                            "平均涨跌": st.column_config.NumberColumn("平均涨跌", format="%.2f%%"),
                            "成交额": st.column_config.NumberColumn("成交额", format="compact"),
                            "股票数": st.column_config.NumberColumn("样本数", format="%,d"),
                        },
                        width="stretch",
                        hide_index=True,
                    )


def render_research_links(stocks,navigation,prefix=''):
    st.subheader("资金研究联动",icon=":material/hub:")
    field=select_market_group_column(stocks)
    if field not in ('行业','细分行业','板块') or field not in stocks or stocks.empty:
        st.info("当前个股快照未包含可用行业字段，暂不能建立资金到个股的研究联动。")
        return
    frame=stocks.copy()
    frame['_child']=frame[field].fillna('').astype(str).str.strip()
    frame['_parent']=frame['行业'].fillna('').astype(str).str.strip() if field=='细分行业' and '行业' in frame else frame['_child']
    frame=frame.loc[frame['_child'].ne('') & frame['_parent'].ne('')]
    options=sorted(set(zip(frame['_parent'],frame['_child'])))
    if not options:
        st.info("当前个股快照未包含可用行业字段。")
        return
    state=navigation.state
    key=prefix+'capital_replay_research_industry'
    if state.get(key) not in options: state[key]=options[0]
    st.selectbox("把行业线索带入研究",options,key=key,
        format_func=lambda pair:f"{pair[0]} › {pair[1]}" if pair[0]!=pair[1] else pair[1])
    st.caption("跳转保留行业及父级上下文；资金板块与个股行业口径未必相同，不推断资金流向单只股票。")
    def open_target(detail=False):
        target=state.get(key)
        if target not in options: return
        parent,value=target
        if not detail:
            navigation.focus_sector(field,value,set(options),parent=parent)
            return
        members=frame.loc[frame['_parent'].eq(parent) & frame['_child'].eq(value)]
        if '代码' not in members: return
        members=members.loc[members['代码'].map(lambda c:isinstance(c,str) and len(c)==6 and c.isascii() and c.isdigit())]
        if members.empty: return
        if '涨跌幅' in members: members=members.sort_values('涨跌幅',ascending=False)
        navigation.open_stock(members.iloc[0]['代码'],set(members['代码']),value,parent)
    with st.container(horizontal=True):
        st.button("在云图定位",key=prefix+'capital_replay_open_terminal',on_click=open_target)
        st.button("查看同业个股",key=prefix+'capital_replay_open_detail',on_click=open_target,args=(True,))


def render_detail(replay,capabilities,state,prefix=''):
    replay_dates=sorted(replay['时间'].astype(str).str[:10].unique())
    def table(frame,**kwargs):
        return public_table(frame,CAPITAL_TABLE_FIELDS,capabilities,**kwargs)
    from ..capital_model import follow_latest_replay_date
    follow_latest_replay_date(state,prefix+'capital_replay_date',replay_dates)
    selected_date = st.selectbox("回放交易日", replay_dates, key=prefix+"capital_replay_date")
    if selected_date not in replay_dates:
        st.warning("资金日期无效。")
        return
    day_replay = filter_capital_replay_by_date(replay, selected_date)
    detail_segments = capital_replay_segments(day_replay)
    with st.container(border=True):
        st.subheader("选定时点明细与行业资金地图", icon=":material/paid:")
        day_timestamps = sorted(day_replay["时间"].astype(str).unique().tolist())
        selected_time = st.selectbox("回放时点", day_timestamps, index=len(day_timestamps) - 1, key=prefix+"capital_replay_time")
        if selected_time not in day_timestamps:
            st.warning("资金时点无效。")
            return
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
        table(
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
            tracked_industry = st.selectbox("查看单一行业全天轨迹", available_industries, key=prefix+"capital_replay_industry")
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
                    table(
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
                    table(
                        changes.sort_values("净流入变化").head(10),
                        column_config={
                            "首时点净流入": st.column_config.NumberColumn("首时点净流入", format="%.0f"),
                            "末时点净流入": st.column_config.NumberColumn("末时点净流入", format="%.0f"),
                            "净流入变化": st.column_config.NumberColumn("净流入变化", format="%.0f"),
                        },
                        width="stretch",
                        hide_index=True,
                    )



def render_flow_charts(day_replay, state, prefix=''):
    """Render user-selected sectors, with bars and tracks using the same selection."""
    from ..capital_taxonomy import CAPITAL_FLOW_SECTORS, canonical_capital_flow_sector
    required = {"时间", "行业", "净流入额"}
    if not required.issubset(day_replay.columns) or day_replay.empty:
        st.info("暂无板块资金快照。采集成功后，这里会出现最新资金偏好和当日走势。", icon=":material/info:")
        return
    segments = capital_replay_segments(day_replay)
    if len(segments) > 1:
        options = [label for label, _ in reversed(segments)]
        key = prefix+"capital_flow_visible_segment"
        newest = options[0]
        if state.get(f"{key}_newest") != newest or state.get(key) not in options:
            state[key] = newest
            state[f"{key}_newest"] = newest
        chosen = st.selectbox("查看资金源片段", options, key=key)
        if chosen not in options:
            st.warning("资金来源选择无效。")
            return
        day_replay = next(frame for label, frame in segments if label == chosen)
        span = day_replay["时间"].astype(str).sort_values()
        st.info(f"当前片段 {span.iloc[0][-5:]}—{span.iloc[-1][-5:]}。资金源切换处已断开，不跨口径连线。")
    else:
        day_replay = segments[0][1]
        st.caption(f"本日资金源：{segments[0][0].split('｜')[0]}。历史日期可能使用其他数据源，净额口径需分别查看。")

    def _migrate_capital_flow_selection(values):
        replacements = {"国产软件": ("软件开发", "游戏"), "医药生物": ("创新药",)}
        migrated = []
        for name in values:
            for candidate in replacements.get(name, (name,)):
                if candidate in CAPITAL_FLOW_SECTORS and candidate not in migrated:
                    migrated.append(candidate)
        return migrated

    selected_key = prefix+"capital_flow_selected_sectors"
    widget_key = prefix+"capital_flow_sector_selection"
    state[selected_key] = _migrate_capital_flow_selection(
        state.get(selected_key, CAPITAL_FLOW_SECTORS)
    )
    if widget_key in state:
        state[widget_key] = _migrate_capital_flow_selection(state[widget_key])

    def _remember_capital_flow_sector_selection():
        state[prefix+"capital_flow_selected_sectors"] = list(
            state.get(prefix+"capital_flow_sector_selection", CAPITAL_FLOW_SECTORS)
        )

    default_selection = ({"default": state[selected_key]}
                         if widget_key not in state else {})
    selected_sectors = st.multiselect(
        "选择关注板块",
        options=CAPITAL_FLOW_SECTORS,
        key=widget_key,
        on_change=_remember_capital_flow_sector_selection,
        help=f"默认全选 {len(CAPITAL_FLOW_SECTORS)} 个板块；选择会同步影响上方分布图和下方走势曲线。",
        **default_selection,
    )
    state[prefix+"capital_flow_selected_sectors"] = list(selected_sectors)
    date_values = day_replay["时间"].dropna().astype(str).str.slice(0, 10) if "时间" in day_replay else pd.Series(dtype=str)
    trade_date = date_values.iloc[0] if not date_values.empty else "unknown-date"
    if not selected_sectors:
        st.info("请至少选择一个板块。", icon=":material/info:")
        return

    frame = day_replay.loc[:, ["时间", "行业", "净流入额"]].copy()
    frame["净流入额"] = pd.to_numeric(frame["净流入额"], errors="coerce")
    frame["时间戳"] = pd.to_datetime(frame["时间"], errors="coerce")
    frame = frame.dropna(subset=["时间戳", "净流入额"])
    minute_of_day = frame["时间戳"].dt.hour * 60 + frame["时间戳"].dt.minute
    in_session = (
        frame["时间戳"].dt.weekday.lt(5)
        & (minute_of_day.between(9 * 60 + 30, 11 * 60 + 30)
           | minute_of_day.between(13 * 60, 15 * 60))
    )
    frame = frame.loc[in_session].copy()
    if frame.empty:
        st.info("所选日期没有 A 股交易时段内的有效资金快照；午休、周末和收市后的数据不绘制。", icon=":material/info:")
        return
    latest_time = frame["时间戳"].max()
    frame["行业"] = frame["行业"].map(canonical_capital_flow_sector)
    frame = frame.loc[frame["行业"].isin(selected_sectors)].copy()
    latest = frame.loc[frame["时间戳"].eq(latest_time)].copy()
    latest = latest.drop_duplicates("行业", keep="last")
    latest_by_sector = latest.set_index("行业")["净流入额"] if not latest.empty else pd.Series(dtype=float)
    display = pd.DataFrame({"行业": selected_sectors})
    display["净流入额"] = display["行业"].map(latest_by_sector)
    missing_sectors = display.loc[display["净流入额"].isna(), "行业"].tolist()
    with st.container(border=True):
        st.subheader("市场资金偏好分布", icon=":material/bar_chart:")
        st.caption(f"{latest_time:%Y-%m-%d %H:%M}｜当前选择 {len(selected_sectors)} 个板块；净流入单位：亿元。")
        if missing_sectors:
            st.caption("本次数据源未返回：" + "、".join(missing_sectors))
        missing_mask = display["净流入额"].isna()
        bar_values = display["净流入额"].fillna(0)
        bars = go.Figure(go.Bar(
            x=bar_values / 1e8,
            y=display["行业"],
            orientation="h",
            width=0.58,
            marker_color=["#475569" if missing else "#22c55e" if value < 0 else "#ef4444"
                          for value, missing in zip(bar_values, missing_mask)],
            text=["暂无" if missing else f"{value / 1e8:+.2f}"
                  for value, missing in zip(display["净流入额"], missing_mask)],
            textposition="outside",
            cliponaxis=False,
            customdata=["本次未采集" if missing else "已采集" for missing in missing_mask],
            hovertemplate="%{y}<br>%{customdata}<br>净流入 %{x:+.2f} 亿<extra></extra>",
        ))
        bars.update_layout(height=max(300, 18 * len(display)), margin=dict(t=4, l=6, r=24, b=4),
                           bargap=0.34,
                           font=dict(size=10),
                           xaxis_title=dict(text="资金净额（亿元）", font=dict(size=10)),
                           yaxis_title=None, showlegend=False,
                           xaxis=dict(zeroline=True, zerolinecolor="#64748b", gridcolor="#1e293b",
                                      tickfont=dict(size=9)),
                           yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=10),
                                      categoryorder="array", categoryarray=list(reversed(selected_sectors))))
        st.plotly_chart(bars, width="stretch", key=prefix+"capital_flow_latest_bars")

    tracked_sector_names = set(frame["行业"].dropna().astype(str))
    selected_industries = [name for name in selected_sectors if name in tracked_sector_names]
    line_data = frame.loc[frame["行业"].isin(selected_industries)].sort_values("时间戳")
    if line_data.empty:
        st.info("所选板块在这些采集时点没有可绘制的资金数据；上方已保留缺数标识。", icon=":material/info:")
        return
    if line_data["时间戳"].nunique() < 2:
        st.info("已记录当前交易时段数据。当前来源片段仅有一个时点，暂不绘制走势；等待后续发布快照。", icon=":material/timeline:")
        return
    line_data = line_data.copy()
    line_data["净流入亿元"] = line_data["净流入额"] / 1e8
    time_points = sorted(line_data["时间戳"].drop_duplicates().tolist())
    time_position = {timestamp: index for index, timestamp in enumerate(time_points)}
    line_data["交易序号"] = line_data["时间戳"].map(time_position)
    tick_step = max(1, (len(time_points) + 7) // 8)
    tick_positions = list(range(0, len(time_points), tick_step))
    if tick_positions[-1] != len(time_points) - 1:
        tick_positions.append(len(time_points) - 1)
    with st.container(border=True):
        st.subheader("当日板块资金流向走势", icon=":material/show_chart:")
        first_time = line_data["时间戳"].min()
        st.caption(f"{first_time:%H:%M}—{latest_time:%H:%M}｜右侧标签按每次采集后的最新净额重新排序；这是各采集时点的数据源累计口径快照，并非逐笔资金流。")
        chart = go.Figure()
        endpoints = []
        for industry in selected_industries:
            track = line_data.loc[line_data["行业"].astype(str).eq(industry)].drop_duplicates("时间戳", keep="last")
            if track.empty:
                continue
            color = px.colors.qualitative.Light24[len(endpoints) % len(px.colors.qualitative.Light24)]
            chart.add_trace(go.Scatter(
                x=track["交易序号"], y=track["净流入亿元"], mode="lines+markers",
                name=industry, line=dict(width=2, color=color), marker=dict(size=4, color=color),
                customdata=track["时间戳"].dt.strftime("%H:%M"),
                hovertemplate=f"{industry}<br>%{{customdata}}<br>%{{y:+.2f}} 亿<extra></extra>",
            ))
            end = track.iloc[-1]
            endpoints.append((industry, int(end["交易序号"]), float(end["净流入亿元"]),
                              color))
        # The latest snapshot determines both the label order and each leader's endpoint.
        endpoints.sort(key=lambda item: (-item[2], item[0]))
        values = line_data["净流入亿元"]
        y_min = min(float(values.min()), 0.0)
        y_max = max(float(values.max()), 0.0)
        y_padding = max((y_max - y_min) * 0.06, 0.5)
        y_min -= y_padding
        y_max += y_padding
        last_position = max(len(time_points) - 1, 1)
        x_padding = 0.2
        for rank, (industry, end_x, end_y, color) in enumerate(endpoints):
            label_y = 0.95 - rank * 0.90 / max(len(endpoints) - 1, 1)
            end_paper_x = 0.74 * (end_x + x_padding) / (last_position + 2 * x_padding)
            end_paper_y = (end_y - y_min) / (y_max - y_min)
            chart.add_shape(type="line", xref="paper", yref="paper",
                            x0=end_paper_x, y0=end_paper_y, x1=0.77, y1=label_y,
                            line=dict(color=color, width=1.2))
            chart.add_annotation(xref="paper", yref="paper", x=0.77, y=label_y,
                                 text=f"{industry} {end_y:+.2f}亿", showarrow=False,
                                 xanchor="left", yanchor="middle", align="left",
                                 width=135, height=18, borderpad=2,
                                 bgcolor="rgba(15, 23, 42, 0.92)",
                                 bordercolor=color, borderwidth=1,
                                 font=dict(size=10, color=color))
        chart.add_hline(y=0, line_color="#64748b", line_width=1)
        chart.update_layout(height=max(480, 34 * len(endpoints)),
                            margin=dict(t=12, l=8, r=12, b=8),
                            xaxis_title="采集时间", yaxis_title="净流入（亿元）",
                            hovermode="x unified", showlegend=False,
                            xaxis=dict(domain=[0, 0.74], range=[-x_padding, last_position + x_padding],
                                       gridcolor="#1e293b", tickmode="array",
                                       tickvals=tick_positions,
                                       ticktext=[time_points[position].strftime("%H:%M") for position in tick_positions]),
                            yaxis=dict(gridcolor="#1e293b", range=[y_min, y_max]))
        st.plotly_chart(chart, width="stretch", key=prefix+"capital_flow_intraday_lines")

