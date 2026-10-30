"""Original heatmap renderer, explicitly injected public data and navigation."""
from math import isfinite
import pandas as pd
import plotly.express as px
import streamlit as st
from ..components import public_table
from .concepts import SECTOR_FIELDS


def render(snapshot,capabilities,navigation):
    stocks=snapshot.stocks
    group=next((field for field in ("行业","细分行业","板块") if field in stocks),None)
    sectors=(stocks.groupby(group,dropna=False,as_index=False).agg(涨跌幅=("涨跌幅","mean"),成交额=("成交额","sum"))
        .rename(columns={group:"板块"})) if group and not stocks.empty else pd.DataFrame()
    st.caption(f"行情交易日：{snapshot.metadata['date']}｜{snapshot.metadata['source']}；底部板块对照为{group or '缺失分类'}聚合，不是概念指数。")
    render_frame(dict(stocks=stocks,sectors=sectors),capabilities,navigation,navigation.namespace+"_")

def render_frame(data,capabilities,navigation,prefix=''):

    def table(frame,**kwargs):
        return public_table(frame,tuple(frame.columns),capabilities,**kwargs)
    def download(*args,**kwargs):
        if capabilities.download: return st.download_button(*args,**kwargs)
    st.title("板块强度与热力图")
    df = data["sectors"][[field for field in SECTOR_FIELDS if field in data["sectors"]]].copy().reset_index(drop=True)
    if df.empty:
        st.warning("当前没有可用板块数据，请先导入数据或检查数据源。")
        return
    if '成交额' not in df or pd.to_numeric(df['成交额'],errors='coerce').fillna(0).sum()<=0:
        st.warning("板块面积规模为零或缺失，暂不绘制面积图；不补造正值规模。")
        return
    stock_df = data.get("stocks", pd.DataFrame()).copy()
    stock_df = stock_df.loc[:, ~stock_df.columns.duplicated()].copy()
    industry_col = "行业" if "行业" in stock_df.columns else "细分行业" if "细分行业" in stock_df.columns else None
    if industry_col and "涨跌幅" in stock_df.columns:
        st.subheader("全行业市场地图")
        toolbar = st.columns([1.15, 1.15, 1.15, 1.15])
        with toolbar[0]:
            map_scope = st.selectbox("地图层级", ["全市场", "行业", "细分行业"], key=prefix+"heatmap_scope")
        with toolbar[1]:
            size_field = st.selectbox("面积指标", [x for x in ("成交额", "流通市值", "总市值") if x in stock_df.columns] or ["成交额"], key=prefix+"heatmap_size")
        with toolbar[2]:
            color_metric = st.selectbox("颜色指标", ["涨跌幅", "上涨占比", "综合评分"], key=prefix+"heatmap_color_metric")
        with toolbar[3]:
            min_amount = st.number_input("最小规模筛选", min_value=0.0, value=0.0, step=1_000_000.0, key=prefix+"heatmap_min_amount")
        heatmap_limit = st.slider("热力图显示数量", 10, 200, 80, 10, key=prefix+"heatmap_limit")
        heatmap_sort = st.selectbox("热力图排序", ["规模优先", "涨跌幅优先"], key=prefix+"heatmap_sort")
        group_cols = [industry_col]
        if map_scope == "细分行业" and "细分行业" in stock_df.columns and industry_col != "细分行业":
            group_cols.append("细分行业")
        if (map_scope not in ("全市场","行业","细分行业") or size_field not in ("成交额","流通市值","总市值")
                or color_metric not in ("涨跌幅","上涨占比","综合评分") or heatmap_sort not in ("规模优先","涨跌幅优先")
                or type(heatmap_limit) is not int or not 10<=heatmap_limit<=200 or not isfinite(float(min_amount)) or min_amount<0):
            st.warning("热力图筛选无效。")
            return
        working = stock_df.copy()
        heat_filter = st.selectbox("快速筛选", ["全部股票", "涨幅超过 5%", "跌幅超过 5%", "上涨股票", "下跌股票"], key=prefix+"heatmap_quick_filter")
        cross_keyword = st.text_input("行业 / 概念交叉筛选", placeholder="输入行业、概念或标签关键词", key=prefix+"heatmap_cross_keyword")
        if heat_filter not in ("全部股票","涨幅超过 5%","跌幅超过 5%","上涨股票","下跌股票"):
            st.warning("快速筛选无效。")
            return
        working["涨跌幅"] = pd.to_numeric(working["涨跌幅"], errors="coerce")
        if heat_filter == "涨幅超过 5%":
            working = working[working["涨跌幅"] >= 5]
        elif heat_filter == "跌幅超过 5%":
            working = working[working["涨跌幅"] <= -5]
        elif heat_filter == "上涨股票":
            working = working[working["涨跌幅"] > 0]
        elif heat_filter == "下跌股票":
            working = working[working["涨跌幅"] < 0]
        if cross_keyword.strip():
            text_cols = [c for c in ("行业", "细分行业", "板块", "标签", "名称") if c in working.columns]
            combined = working[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
            working = working[combined.str.contains(cross_keyword.strip(), case=False, regex=False)]
        if working.empty:
            st.warning("当前筛选没有有效股票；不补造行业行情或零值。")
            return
        for col in group_cols:
            working[col] = working[col].fillna("").astype(str).str.strip()
            working.loc[working[col].isin(["", "nan", "None", "—", "--"]), col] = "未细分" if col == "细分行业" else "未分类"
        working[size_field] = pd.to_numeric(working.get(size_field, pd.Series(index=working.index)), errors="coerce").fillna(0)
        industry_map = working.dropna(subset=[industry_col]).groupby(group_cols, dropna=False).agg(成交额=(size_field, "sum"), 涨跌幅=("涨跌幅", "mean"), 股票数=("代码", "count") if "代码" in working.columns else (industry_col, "count")).reset_index()
        industry_map["路径"] = "全市场"
        industry_summary = working.dropna(subset=[industry_col]).groupby(industry_col, dropna=False).agg(
            成交额=(size_field, "sum"), 涨跌幅=("涨跌幅", "mean"),
            股票数=("代码", "count") if "代码" in working.columns else (industry_col, "count"),
            上涨占比=("涨跌幅", lambda x: float((x > 0).mean()) if x.notna().any() else float("nan")),
        ).reset_index()
        industry_summary["综合评分"] = (industry_summary["涨跌幅"].rank(pct=True) * 50 + industry_summary["上涨占比"].rank(pct=True) * 30 + industry_summary["成交额"].rank(pct=True) * 20).round(1)
        industry_map["上涨占比"] = industry_map[industry_col].map(industry_summary.set_index(industry_col)["上涨占比"])
        industry_map["综合评分"] = industry_map[industry_col].map(industry_summary.set_index(industry_col)["综合评分"])
        display_map = industry_map[industry_map["成交额"] >= min_amount].copy()
        display_map = display_map.sort_values("成交额" if heatmap_sort == "规模优先" else "涨跌幅", ascending=False).head(int(heatmap_limit))
        map_left, map_right = st.columns([4, 1])
        with map_left:
            midpoint = 0.5 if color_metric == "上涨占比" else 0
            if display_map.empty or display_map["成交额"].sum()<=0:
                st.warning("当前规模筛选下没有行业，请降低最小规模。")
            else:
                map_fig = px.treemap(display_map, path=["路径", *group_cols], values="成交额", color=color_metric, hover_data=["股票数", "上涨占比"], color_continuous_scale="RdYlGn", color_continuous_midpoint=midpoint)
                map_fig.update_traces(textinfo="label+value+percent parent", textfont_size=13, marker_line_width=1, marker_line_color="#111827")
                color_title = {"涨跌幅": "涨跌", "上涨占比": "上涨占比", "综合评分": "综合评分"}[color_metric]
                map_fig.update_layout(margin=dict(t=8, l=4, r=4, b=4), height=650, coloraxis_colorbar=dict(title=color_title))
                st.plotly_chart(map_fig, width="stretch")
                download("导出当前热力图数据 CSV", display_map.to_csv(index=False, encoding="utf-8-sig"), "market_heatmap.csv", "text/csv")
        with map_right:
            avg_change = pd.to_numeric(working["涨跌幅"], errors="coerce").dropna()
            map_right.metric("行业数量", display_map[industry_col].nunique())
            map_right.metric("上涨行业", int((display_map["涨跌幅"] > 0).sum()))
            map_right.metric("下跌行业", int((display_map["涨跌幅"] < 0).sum()))
            map_right.metric("平均涨跌", f"{avg_change.mean():+.2f}%" if not avg_change.empty else "暂无")
            breadth = pd.DataFrame({"方向": ["上涨", "平盘", "下跌"], "数量": [int((working["涨跌幅"] > 0).sum()), int((working["涨跌幅"] == 0).sum()), int((working["涨跌幅"] < 0).sum())]})
            breadth_fig = px.bar(breadth, x="数量", y="方向", orientation="h", color="方向", color_discrete_map={"上涨":"#16a34a", "平盘":"#64748b", "下跌":"#dc2626"})
            breadth_fig.update_layout(height=190, margin=dict(t=12, l=0, r=0, b=0), showlegend=False)
            st.plotly_chart(breadth_fig, width="stretch")
            st.caption("涨跌结构")
            if not industry_summary.empty and "综合评分" in industry_summary.columns:
                best_industry = industry_summary.sort_values("综合评分", ascending=False).iloc[0]
                st.metric("综合评分最高行业", str(best_industry[industry_col]), f"{best_industry['综合评分']:.1f}")
        st.caption(f"{map_scope}热力图来自最近一次导入的全市场快照；面积为{size_field}，颜色可按涨跌幅、上涨占比或综合评分展示。")
        industry_options = sorted(industry_map[industry_col].astype(str).unique().tolist())
        selected_industry = st.selectbox("查看行业成分股", industry_options, key=prefix+"heatmap_industry")
        if selected_industry not in industry_options:
            st.warning("行业选择无效。")
            return
        st.subheader("云图研究路径", icon=":material/account_tree:")
        st.caption("热力图用于定位行业强弱；进入大盘云图后可查看完整行业结构与个股叶子节点，再进入个股详情做同类比较。")
        def open_selected(detail=False):
            current=navigation.state.get(prefix+"heatmap_industry")
            if current not in industry_options: return
            rows=working.loc[working[industry_col].astype(str).eq(current)].sort_values("涨跌幅",ascending=False)
            if detail:
                if not rows.empty: navigation.open_stock(rows.iloc[0]["代码"],set(stock_df["代码"]),current,current)
            else:
                navigation.focus_sector(industry_col,current,{(value,value) for value in industry_options},parent=current)
        with st.container(horizontal=True,vertical_alignment="bottom"):
            st.button("在大盘云图定位行业",icon=":material/filter_alt:",key=prefix+"heatmap_open_terminal",on_click=open_selected)
            st.button("进入个股详情",icon=":material/description:",key=prefix+"heatmap_open_detail",on_click=open_selected,args=(True,))
        members = working[working[industry_col].astype(str) == selected_industry].copy()
        members["涨跌幅"] = pd.to_numeric(members["涨跌幅"], errors="coerce")
        members = members.sort_values(["涨跌幅", size_field], ascending=[False, False])
        member_view = st.selectbox("成分股分层", ["全部成分股", "强势股（涨幅前 10）", "弱势股（跌幅前 10）", "高成交额前 10"], key=prefix+"heatmap_member_view")
        if member_view not in ("全部成分股","强势股（涨幅前 10）","弱势股（跌幅前 10）","高成交额前 10"):
            st.warning("成分股分层无效。")
            return
        if member_view == "强势股（涨幅前 10）":
            members = members.nlargest(10, "涨跌幅")
        elif member_view == "弱势股（跌幅前 10）":
            members = members.nsmallest(10, "涨跌幅")
        elif member_view == "高成交额前 10":
            members = members.sort_values(size_field, ascending=False).head(10)
        st.subheader(f"{selected_industry} 行业成分股")
        member_cols = [c for c in ("代码", "名称", "涨跌幅", size_field, "换手率", "细分行业", "板块") if c in members.columns]
        table(members[member_cols].head(50), width="stretch", hide_index=True)
        download("导出当前行业成分股 CSV", members[member_cols].to_csv(index=False, encoding="utf-8-sig"), "industry_members.csv", "text/csv")
        member_change = pd.to_numeric(members["涨跌幅"], errors="coerce").dropna()
        detail_cards = st.columns(4)
        detail_cards[0].metric("行业股票数", f"{len(members):,}")
        detail_cards[1].metric("上涨占比", f"{(member_change > 0).mean():.1%}" if not member_change.empty else "暂无")
        detail_cards[2].metric("平均涨跌", f"{member_change.mean():+.2f}%" if not member_change.empty else "暂无")
        detail_cards[3].metric("最大涨幅", f"{member_change.max():+.2f}%" if not member_change.empty else "暂无")
        st.caption(f"当前行业覆盖 {len(members):,} 只股票，数据来自最近一次导入快照。")
        if "名称" in members.columns and members["涨跌幅"].notna().any():
            winner_col, loser_col = st.columns(2)
            with winner_col:
                st.subheader("行业涨幅居前")
                st.bar_chart(members.nlargest(10, "涨跌幅").set_index("名称")["涨跌幅"])
            with loser_col:
                st.subheader("行业跌幅居前")
                st.bar_chart(members.nsmallest(10, "涨跌幅").set_index("名称")["涨跌幅"])
        if "细分行业" in members.columns:
            subindustry = members.groupby("细分行业", dropna=False).agg(平均涨跌=("涨跌幅", "mean"), 股票数=("代码", "count") if "代码" in members.columns else (industry_col, "count")).reset_index()
            st.subheader("细分行业强弱")
            st.bar_chart(subindustry.sort_values("平均涨跌", ascending=False).head(20).set_index("细分行业")["平均涨跌"])
        rank_left, rank_right = st.columns(2)
        with rank_left:
            st.subheader("行业强弱排行")
            table(industry_summary.sort_values("综合评分", ascending=False).head(15)[[industry_col, "综合评分", "涨跌幅", "上涨占比", "股票数"]], width="stretch", hide_index=True)
            download("导出行业强弱排行 CSV", industry_summary.sort_values("涨跌幅", ascending=False).to_csv(index=False, encoding="utf-8-sig"), "industry_strength.csv", "text/csv")
        with rank_right:
            st.subheader("行业成交额排行")
            table(industry_summary.sort_values("成交额", ascending=False).head(15)[[industry_col, "成交额", "涨跌幅", "股票数"]], width="stretch", hide_index=True)
        st.subheader("行业涨跌分布")
        dist = pd.DataFrame({"行业": industry_summary[industry_col].astype(str), "涨跌幅": pd.to_numeric(industry_summary["涨跌幅"], errors="coerce")}).dropna()
        dist_fig = px.histogram(dist, x="涨跌幅", nbins=18, color_discrete_sequence=["#2dd4bf"])
        dist_fig.add_vline(x=0, line_dash="dot", line_color="#f8fafc")
        dist_fig.update_layout(height=260, margin=dict(t=10, l=0, r=0, b=0), xaxis_title="行业平均涨跌幅（%）", yaxis_title="行业数量")
        st.plotly_chart(dist_fig, width="stretch")
        st.subheader("行业综合评分")
        score_view = industry_summary.sort_values("综合评分", ascending=False).head(20).sort_values("综合评分")
        st.plotly_chart(px.bar(score_view, x="综合评分", y=industry_col, orientation="h", color="综合评分", color_continuous_scale="Viridis"), width="stretch")
        st.subheader("行业强度与广度")
        st.plotly_chart(px.scatter(industry_summary, x="上涨占比", y="涨跌幅", size="成交额", color="涨跌幅", hover_name=industry_col, hover_data=["股票数"], color_continuous_scale="RdYlGn", color_continuous_midpoint=0), width="stretch")
        distribution_left, distribution_right = st.columns(2)
        with distribution_left:
            st.subheader("行业覆盖度")
            st.bar_chart(industry_summary.sort_values("股票数", ascending=False).head(20).set_index(industry_col)["股票数"])
        with distribution_right:
            st.subheader("行业内活跃个股")
            leaders = working.sort_values([size_field, "涨跌幅"], ascending=[False, False]).groupby(industry_col, as_index=False).first()
            leader_cols = [c for c in (industry_col, "代码", "名称", "涨跌幅", size_field) if c in leaders.columns]
            table(leaders[leader_cols].sort_values(size_field, ascending=False).head(20), width="stretch", hide_index=True)
            download("导出行业活跃龙头 CSV", leaders[leader_cols].sort_values(size_field, ascending=False).head(20).to_csv(index=False, encoding="utf-8-sig"), "industry_leaders.csv", "text/csv")
    fig = px.treemap(df, path=["板块"], values="成交额", color="涨跌幅", color_continuous_scale="RdYlGn", color_continuous_midpoint=0)
    fig.update_traces(textinfo="label+value", marker_line_width=1, marker_line_color="#111827")
    fig.update_layout(margin=dict(t=8, l=4, r=4, b=4), height=560)
    st.plotly_chart(fig, width="stretch")
    st.subheader("板块强弱对照")
    left, right = st.columns(2)
    with left:
        table(df.sort_values("涨跌幅", ascending=False).head(10), width="stretch", hide_index=True)
    with right:
        table(df.sort_values("涨跌幅", ascending=True).head(10), width="stretch", hide_index=True)
    st.subheader("板块成交额与涨跌幅明细")
    detail = df.copy()
    detail["成交额"] = pd.to_numeric(detail.get("成交额", pd.Series(index=detail.index)), errors="coerce")
    detail["涨跌幅"] = pd.to_numeric(detail.get("涨跌幅", pd.Series(index=detail.index)), errors="coerce")
    table(detail.sort_values("成交额", ascending=False).head(30), width="stretch", hide_index=True)
    download("导出板块热力数据 CSV", detail.to_csv(index=False, encoding="utf-8-sig"), "sector_heatmap.csv", "text/csv")

