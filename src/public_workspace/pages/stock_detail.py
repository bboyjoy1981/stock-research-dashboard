"""Original final stock-detail workspace over injected public observations."""
import pandas as pd
import plotly.express as px
import streamlit as st
from ...calculations import stock_top_percent,stock_snapshot_history,stock_relative_snapshot,research_context_label
from ...recent_research import remember_stock
from ..contracts import PublicSnapshot
from ..scanner_model import quote_detail_values,select_market_group_column
from ..detail_model import market_group_coverage,valid_peer_group_fields,rank_peer_quotes,quote_export,_ashare_change_style
from ..components import public_table
from .daily import render as render_daily
from .stock_comparison import render as render_stock_snapshot_comparison


def open_peer_from_state(state,prefix,navigation,choices,allowed_codes):
    label=state.get(prefix+'detail_peer_jump')
    if label not in choices: return False
    code=label.split(' · ',1)[0]
    if not navigation.open_stock(code,allowed_codes): return False
    state[prefix+'stock_detail_query']=code
    state.pop(prefix+'stock_detail_selection',None)
    return True


def focus_matches(frame,context):
    # Exact parent/child paths, never substring matching across unrelated groups.
    if not isinstance(context,dict): return frame.copy()
    field=context.get("field")
    value=context.get("industry")
    if field is None and isinstance(value,str):
        # Old owner callbacks supplied only the label; infer exact membership,
        # never expand it as a substring into similarly named industries.
        field=next((name for name in ('行业','细分行业','板块')
                    if name in frame and frame[name].eq(value).any()),None)
        if field is None: return frame.iloc[:0].copy()
        if field=='细分行业' and not context.get('parent') and '行业' in frame:
            parents=frame.loc[frame[field].eq(value),'行业'].dropna().unique()
            if len(parents)==1: context=dict(context,parent=parents[0])
    if field not in ("行业","细分行业","板块") or field not in frame or not isinstance(value,str):
        return frame.copy()
    mask=frame[field].eq(value)
    if field=="细分行业":
        parent=context.get("parent")
        if not isinstance(parent,str) or "行业" not in frame: return frame.iloc[:0].copy()
        mask &= frame["行业"].eq(parent)
    return frame.loc[mask].copy()


def quote_origin(data):
    if data.get("public_source"):
        return f"公开行情快照｜截至交易日：{data['import_date']}｜{data['public_source']}"
    if data.get("stock_quote_source")=="imported":
        return f"导入行情快照｜截至交易日：{data.get('import_date') or '未识别'}"
    return "演示行情｜非真实市场报价"


def render(snapshot,capabilities,navigation):
    # Reconstruct to re-prune mutable dataframe fields before any table/chart/audit.
    snapshot=PublicSnapshot(snapshot.stocks,snapshot.indices,dict(snapshot.metadata),dict(snapshot.optional))
    old=snapshot.optional.get("history")
    observed=old.frame.copy() if old is not None else pd.DataFrame()
    current=snapshot.stocks.assign(快照日期=snapshot.metadata["date"],快照来源=snapshot.metadata["source"])
    observed=pd.concat([observed,current],ignore_index=True)
    data=dict(stocks=snapshot.stocks,import_date=snapshot.metadata["date"],stock_quote_source="imported",
        market_history=observed,daily_history=snapshot.optional.get("daily_history"),
        public_source=snapshot.metadata["source"])
    render_frame(data,capabilities,navigation,navigation.namespace+"_")

def render_frame(data, capabilities, navigation, prefix="", daily_renderer=None):

    state=navigation.state
    allowed_codes=set(data.get("stocks",pd.DataFrame()).get("代码",pd.Series(dtype=str)))
    external_code=state.get(prefix+"code")
    if external_code in allowed_codes and external_code!=state.get(prefix+"detail_synced_code"):
        state[prefix+"stock_detail_query"]=external_code
        state.pop(prefix+"stock_detail_selection",None)
        state[prefix+"detail_synced_code"]=external_code

    def table(frame,**kwargs):
        # Styler inputs are owner-only; guests receive a physically pruned frame.
        if capabilities.download:
            return st.dataframe(frame,**kwargs)
        if not isinstance(frame,pd.DataFrame): frame=frame.data
        return public_table(frame,tuple(frame.columns),capabilities,**kwargs)
    def download(*args,**kwargs):
        if capabilities.download: return st.download_button(*args,**kwargs)
    def _reset_detail_selection():
        state.pop(prefix+"stock_detail_selection",None)
        state.pop(prefix+"code",None)
    def _clear_detail_search():
        _reset_detail_selection()
        state[prefix+"stock_detail_query"]=""
        state.pop(prefix+"research_context",None)
    def _select_detail_neighbor(label):
        state[prefix+"stock_detail_selection"]=label
    def _open_peer_stock(choices):
        # Read the updated widget state, not a previous-run captured selection.
        return open_peer_from_state(state,prefix,navigation,choices,allowed_codes)
    def open_sector_cloud(field,value,parent):
        frame=data["stocks"]
        if field not in frame: return
        if field=="细分行业":
            if "行业" not in frame: return
            pairs=set(zip(frame["行业"],frame[field]))
        else:
            parent=value
            pairs={(v,v) for v in frame[field].dropna().astype(str)}
        navigation.focus_sector(field,value,pairs,parent)
    def render_context(context):
        label=research_context_label(context)
        if not label: return
        with st.container(horizontal=True,vertical_alignment="center"):
            st.info(label,icon=":material/route:")
            st.button("定位云图",icon=":material/account_tree:",key=prefix+"research_path_cloud_detail",
                on_click=navigation.open_page,args=("大盘云图",))
            st.button("查看同业",icon=":material/query_stats:",key=prefix+"research_path_peers_detail",
                on_click=navigation.open_page,args=("个股详情",))
            st.button("清除路径",icon=":material/close:",key=prefix+"clear_research_context_detail",
                on_click=_clear_detail_search)

    st.subheader("个股详情 · 快照研究卡", icon=":material/query_stats:")
    df = data.get("stocks", pd.DataFrame()).copy()
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if df.empty or "代码" not in df.columns:
        st.warning("当前没有可用个股数据")
        return
    df["代码"] = df["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    for field in ("价格", "涨跌幅", "成交额", "流通市值", "总市值", "换手率", "量比", "综合分", "风险分"):
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors="coerce")
    research_context = state.get(prefix+"research_context", {})
    search_col, selection_col, clear_col = st.columns([1, 1.35, .42], vertical_alignment="bottom")
    with search_col:
        query = st.text_input("搜索代码或名称", placeholder="例如 688008、澜起科技、中际旭创", key=prefix+"stock_detail_query", persist_state="session", on_change=_reset_detail_selection)
    with clear_col:
        st.button("全市场搜索", icon=":material/search_off:", key=prefix+"detail_clear_search", on_click=_clear_detail_search, width="stretch")
    name_series = df["名称"].fillna("").astype(str) if "名称" in df.columns else pd.Series("", index=df.index)
    matches = df[df["代码"].str.contains(query.strip(), case=False, regex=False) | name_series.str.contains(query.strip(), case=False, regex=False)] if query.strip() else df.copy()
    focused_matches = focus_matches(matches, research_context)
    if not query.strip() and research_context_label(research_context):
        matches = focused_matches
        st.caption(f"已按{research_context_label(research_context).replace('当前研究路径：', '')}筛选同业个股；输入代码或名称可改为全市场搜索。")
    if "成交额" in matches.columns:
        matches = matches.sort_values("成交额", ascending=False)
    matches = matches.head(300)
    if matches.empty:
        st.info("没有匹配的股票")
        return
    labels = (matches["代码"].astype(str) + " · " + name_series.loc[matches.index].replace("", "未命名")).tolist()
    with selection_col:
        selected_label = st.selectbox("选择股票", labels, key=prefix+"stock_detail_selection", persist_state="session")
    if selected_label not in labels:
        st.warning("股票选择无效。")
        return
    selected_code = selected_label.split(" · ", 1)[0]
    row = df[df["代码"] == selected_code].iloc[0]
    state[prefix+"recent_research_stocks"] = remember_stock(
        state.get(prefix+"recent_research_stocks", []), selected_code, row["名称"],
    )
    selected_position = labels.index(selected_label)
    detail_actions = st.container(horizontal=True)
    with detail_actions:
        cloud_field = next((field for field in ('细分行业', '行业', '板块')
                            if field in df and pd.notna(row.get(field))
                            and str(row[field]).strip() not in {'', '未分类', '未细分'}
                            and market_group_coverage(df, field)['coverage'] >= .15), None)
        st.button('所属行业云图', icon=':material/account_tree:', key=prefix+'detail_industry_cloud',
                  disabled=cloud_field is None, on_click=open_sector_cloud,
                  args=(cloud_field, str(row.get(cloud_field, '')),
                        str(row.get('行业')) if cloud_field == '细分行业' and pd.notna(row.get('行业')) else None))
        st.button(
            "上一只", icon=":material/chevron_left:", key=prefix+"detail_previous_stock",
            disabled=selected_position == 0, on_click=_select_detail_neighbor,
            args=(labels[max(0, selected_position - 1)],),
        )
        st.button(
            "下一只", icon=":material/chevron_right:", key=prefix+"detail_next_stock",
            disabled=selected_position == len(labels) - 1, on_click=_select_detail_neighbor,
            args=(labels[min(len(labels) - 1, selected_position + 1)],),
        )
        st.caption(f"当前候选 {selected_position + 1}/{len(labels)}")
        download(
            "导出个股快照", quote_export(row.to_frame().T, data).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{selected_code}_{data.get('import_date') or '快照'}.csv",
            mime="text/csv", icon=":material/download:", key=prefix+"detail_export_snapshot",
        )

    def value(field, default="—"):
        item = row.get(field, default)
        return default if pd.isna(item) else item

    price = pd.to_numeric(pd.Series([value("价格", None)]), errors="coerce").iloc[0]
    change = pd.to_numeric(pd.Series([value("涨跌幅", None)]), errors="coerce").iloc[0]
    amount = pd.to_numeric(pd.Series([value("成交额", None)]), errors="coerce").iloc[0]
    market_change = pd.to_numeric(df.get("涨跌幅", pd.Series(dtype=float)), errors="coerce")
    relative_rank = float(market_change.rank(pct=True).loc[row.name] * 100) if row.name in market_change.index and pd.notna(market_change.loc[row.name]) else None
    market_top_percent = stock_top_percent(change, market_change)
    status = "强势" if pd.notna(change) and change >= 3 else "偏强" if pd.notna(change) and change > 0 else "偏弱" if pd.notna(change) and change > -3 else "弱势" if pd.notna(change) else "待补数据"

    st.caption(f"{quote_origin(data)}；用于研究、比较和复盘，不代表实时行情或买卖建议。")
    render_context(research_context)
    with detail_actions:
        with st.popover("返回其他市场页面", icon=":material/arrow_back:"):
            if st.button("查看市场总览", icon=":material/dashboard:", key=prefix+"detail_open_overview"):
                navigation.open_page("市场总览")
                st.rerun()
            if st.button("返回大盘云图", icon=":material/account_tree:", key=prefix+"detail_open_terminal"):
                navigation.open_page("大盘云图")
                st.rerun()
    with st.container(border=True, key=prefix+"detail_quote_surface"):
        identity, quote = st.columns([1, 2.4], vertical_alignment="center")
        with identity:
            st.subheader(f"{selected_code} · {value('名称')}")
            with st.container(horizontal=True):
                st.badge(status, icon=":material/analytics:", color="red" if status in {"强势", "偏强"} else "green" if status in {"偏弱", "弱势"} else "gray")
                seen_labels = set()
                for field in ("板块", "行业", "细分行业"):
                    label = str(value(field, "")).strip()
                    if label and label not in {"未分类", "—", "nan", "None"} and label not in seen_labels:
                        st.badge(label, color="blue")
                        seen_labels.add(label)
        with quote:
            with st.container(horizontal=True):
                st.metric("最新价", f"{price:.2f}" if pd.notna(price) else "—", f"{change:+.2f}%" if pd.notna(change) else None, delta_color="inverse")
                st.metric("成交额", f"{amount / 1e8:.2f} 亿" if pd.notna(amount) else "—")
                st.metric("市场涨幅排名", f"前 {market_top_percent:.0f}%" if relative_rank is not None else "—")
                current_turnover = pd.to_numeric(pd.Series([value("换手率", None)]), errors="coerce").iloc[0]
                st.metric("换手率", f"{current_turnover:.2f}%" if pd.notna(current_turnover) else "—")
    industry_read = next(
        (str(value(field)) for field in ("细分行业", "行业", "板块") if field in df.columns and str(value(field)) not in {"", "—", "nan", "未分类"}),
        "未分类",
    )
    turnover = pd.to_numeric(pd.Series([value("换手率", None)]), errors="coerce").iloc[0]
    st.caption(f"研究归属：{industry_read}｜换手率：{turnover:.2f}%" if pd.notna(turnover) else f"研究归属：{industry_read}｜换手率：待导入")
    quote_facts = quote_detail_values(row)
    detail_tabs = st.tabs(
        ['同业比较', '行情画像', '历史复盘', '数据核对'],
        default='行情画像', key=prefix+'detail_workspace', on_change='rerun',
    )
    if detail_tabs[1].open:
      with detail_tabs[1]:
        st.subheader('当日走势与量价', icon=':material/show_chart:')
        st.caption(f"行情交易日：{data.get('import_date') or '未提供'}｜收盘快照，不是实时行情")
        with st.container(border=True):
            st.info('尚未接入分钟行情，暂不绘制当日分时曲线；收盘快照无法还原盘中价格路径。')
            st.caption('后续接入真实分钟数据后，这里展示全天价格走势和分时成交量；当前不使用模拟曲线。')
        with st.container(horizontal=True):
            for field, label in [('今开', '开盘'), ('最高', '最高'), ('最低', '最低'), ('昨收', '昨收')]:
                number = pd.to_numeric(pd.Series([value(field, None)]), errors='coerce').iloc[0]
                st.metric(label, f'{number:.2f}' if pd.notna(number) else '—')
        with st.container(horizontal=True):
            volume = pd.to_numeric(pd.Series([value('成交量', None)]), errors='coerce').iloc[0]
            st.metric('成交量（原始单位）', f'{volume:,.0f}' if pd.notna(volume) else '—')
            st.metric('成交额', f'{amount / 1e8:.2f} 亿' if pd.notna(amount) else '—')
            ratio = pd.to_numeric(pd.Series([value('量比', None)]), errors='coerce').iloc[0]
            st.metric('量比', f'{ratio:.2f}' if pd.notna(ratio) else '—')
        st.caption('成交量单位沿用导出文件，未确认单位前不自动换算为股或手；缺失数据保持 —。')
        st.divider()
        if daily_renderer is not None and navigation.namespace=='owner':
            daily_renderer(selected_code)
        else:
            render_daily(data.get('daily_history'),selected_code,capabilities,state,prefix,
                         through_date=data.get('import_date'))
    with detail_tabs[0]:
        peer_board = st.container(border=True)
        peer_board.subheader('同类对比', icon=':material/compare_arrows:')
    with detail_tabs[3].expander("开高低昨收与基础信息", expanded=True, icon=":material/fact_check:"):
        st.subheader("快照行情核对", icon=":material/fact_check:")
        quote_col, identity_col = st.columns([1, 1.35], vertical_alignment="top")
        with quote_col:
            st.table(quote_facts, border="horizontal", width="stretch")
        with identity_col:
            st.table({"交易日": data.get("import_date") or "未提供", "研究归属": industry_read,
                      "换手率": f"{turnover:.2f}%" if pd.notna(turnover) else "—",
                      "量比": value("量比")}, border="horizontal", width="stretch")
        available = sum(item != "—" for item in quote_facts.values())
        st.caption(f"开高低昨收覆盖：{available}/4；缺失字段显示 —，不由最新价推算。")

    # Reserve the primary comparison surface above secondary research details.
    # Peer calculations below populate this slot after their scope is resolved.
    with detail_tabs[2].expander("多日个股复盘 · 历史与明细", expanded=True, icon=":material/timeline:"):
        st.subheader("多日个股复盘")
        st.caption("仅连接本地已保存的收盘快照；不是分时行情，缺失交易日不插值。")
        stock_history = stock_snapshot_history(
            data.get("market_history", pd.DataFrame()), selected_code,
            through_date=data.get("import_date"),
        ) if data.get("stock_quote_source") == "imported" else pd.DataFrame()
        if stock_history.empty:
            st.info("当前没有这只股票的历史收盘快照；导入下一交易日数据后可形成多日复盘。")
        elif len(stock_history) < 2:
            st.info(f"目前仅有 {stock_history.iloc[0]['交易日']} 一天的已保存快照，暂不能绘制趋势。")
        else:
            render_stock_snapshot_comparison(stock_history, selected_code,capabilities,prefix)
            metric_options = {label: field for label, field in (("收盘价", "价格"), ("当日涨跌", "涨跌幅"), ("成交额", "成交额")) if stock_history[field].notna().sum() >= 2}
            if metric_options:
                chosen_metric = st.segmented_control("历史观察指标", list(metric_options), default=next(iter(metric_options)), key=prefix+"stock_history_metric")
                chart_frame = stock_history.set_index("交易日")[[metric_options[chosen_metric]]].rename(columns={metric_options[chosen_metric]: chosen_metric})
                if chosen_metric == "成交额":
                    st.bar_chart(chart_frame, height=240)
                else:
                    st.line_chart(chart_frame, height=240)
            else:
                st.info("已保存多个日期，但价格、涨跌幅和成交额均不足两个有效观测值。")
            with st.expander("核对历史快照明细"):
                table(stock_history, width="stretch", hide_index=True)
        if not stock_history.empty:
            download("导出个股历史快照", quote_export(stock_history, data).to_csv(index=False).encode("utf-8-sig"), f"{selected_code}_历史快照.csv", "text/csv", key=prefix+"detail_history_export")

    with detail_tabs[1].expander("个股深度研究 · 画像与指标", expanded=False, icon=":material/analytics:"):
        factor_labels = {
            "涨跌强度": "涨跌幅",
            "成交活跃": "成交额",
            "换手活跃": "换手率",
            "量能变化": "量比",
            "综合评分": "综合分",
        }
        factor_rows = []
        for label, field in factor_labels.items():
            if field not in df.columns or pd.isna(value(field, None)):
                continue
            series = pd.to_numeric(df[field], errors="coerce").dropna()
            current = pd.to_numeric(pd.Series([value(field, None)]), errors="coerce").iloc[0]
            if series.empty or pd.isna(current):
                continue
            percentile = float((series <= current).mean() * 100)
            factor_rows.append({"维度": label, "相对分位": round(percentile, 1)})
        if factor_rows:
            factor_frame = pd.DataFrame(factor_rows)
            snapshot_score = int(round(factor_frame["相对分位"].mean()))
            signal_left, signal_right = st.columns([0.8, 2.2], vertical_alignment="center")
            with signal_left:
                with st.container(border=True):
                    st.metric("快照信号", f"{snapshot_score}/100")
                    st.progress(snapshot_score / 100, text="同市场相对位置")
                    st.caption("以导入快照的横向分位计算；不是预测或交易指令。")
            with signal_right:
                with st.container(border=True):
                    signal_chart = px.bar(
                        factor_frame.sort_values("相对分位"),
                        x="相对分位", y="维度", orientation="h", color="相对分位",
                        color_continuous_scale="RdYlGn_r", range_color=[0, 100],
                    )
                    signal_chart.update_layout(height=190, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="市场相对分位（%）", yaxis_title="")
                    st.plotly_chart(signal_chart, width="stretch")

        profile_left, profile_right = st.columns([1.15, 1.85], vertical_alignment="top")
        with profile_left:
            with st.container(border=True):
                st.subheader("研究画像")
                profile = {field: value(field) for field in ("板块", "行业", "细分行业", "标签") if field in df.columns and str(value(field)) not in {"", "—", "nan"}}
                if profile:
                    st.table(profile, border="horizontal", width="stretch")
                else:
                    st.caption("暂无行业或题材标签")
                st.caption(f"当日状态：{status}" + (f"｜相对全市场涨幅位置约前 {market_top_percent:.0f}%" if relative_rank is not None else ""))
        with profile_right:
            with st.container(border=True):
                st.subheader("关键指标")
                detail_fields = [field for field in ("换手率", "量比", "成交量", "总市值", "流通市值", "综合分", "风险分") if field in df.columns]
                if detail_fields:
                    details = pd.DataFrame([{"指标": field, "数值": value(field)} for field in detail_fields])
                    details["数值"] = pd.to_numeric(details["数值"], errors="coerce")
                    table(details, column_config={"数值": st.column_config.NumberColumn("数值", format="compact")}, width="stretch", hide_index=True)
                else:
                    st.caption("导入文件未提供更多交易及估值字段。")

    preferred_peer_field = select_market_group_column(df)
    peer_order = [preferred_peer_field, "板块", "行业", "细分行业"]
    peer_candidates = list(dict.fromkeys(field for field in peer_order if field in df.columns))
    peer_options = valid_peer_group_fields(df, row.name, peer_candidates)
    peer_field = None
    if peer_options:
        peer_field = peer_board.segmented_control("同类比较口径", peer_options, default=peer_options[0], key=prefix+"stock_detail_peer_scope")
    if peer_field is not None and peer_field not in peer_options:
        st.warning("同类比较口径无效。")
        return
    peers = pd.DataFrame()
    if peer_field:
        peers = df[(df[peer_field].astype(str) == str(value(peer_field))) & (df["代码"] != selected_code)].copy()
    if peer_field=="细分行业" and "行业" in df:
        peers=peers.loc[peers["行业"].eq(row.get("行业"))]
    peer_rank = None
    peer_top_percent = None
    peer_average = None
    if not peers.empty:
        peers["涨跌幅"] = pd.to_numeric(peers.get("涨跌幅"), errors="coerce")
        peer_average = float(peers["涨跌幅"].mean()) if peers["涨跌幅"].notna().any() else None
        if pd.notna(change):
            combined = pd.concat([peers[["涨跌幅"]], pd.DataFrame({"涨跌幅": [change]})], ignore_index=True)
            peer_rank = float(combined["涨跌幅"].rank(pct=True).iloc[-1] * 100)
            peer_top_percent = stock_top_percent(change, combined["涨跌幅"])
    if peer_field and not peers.empty:
        peer_best = float(peers["涨跌幅"].max()) if peers["涨跌幅"].notna().any() else None
        peer_metrics = peer_board.columns(4)
        peer_metrics[0].metric("同类样本", f"{len(peers):,} 只", border=True)
        peer_metrics[1].metric("同类平均", f"{peer_average:+.2f}%" if peer_average is not None else "—", border=True)
        peer_metrics[2].metric("同类最高涨幅", f"{peer_best:+.2f}%" if peer_best is not None else "—", border=True)
        peer_metrics[3].metric(
            "相对同类",
            f"{change - peer_average:+.2f}%" if peer_average is not None and pd.notna(change) else "—",
            f"前 {peer_top_percent:.0f}%" if peer_rank is not None else None,
            delta_color="inverse",
            border=True,
        )
    peer_changes = peers["涨跌幅"] if not peers.empty and "涨跌幅" in peers.columns else []
    relative_snapshot = stock_relative_snapshot(change, market_change, peer_changes)
    with detail_tabs[3].expander("盘后结论与核对清单", expanded=True, icon=":material/checklist:"):
        if relative_snapshot["个股涨跌"] is not None:
            st.subheader("相对位置坐标", icon=":material/radar:")
            st.caption("把当前个股放在全市场与所选同类口径中横向比较。数值来自最近导入快照，不代表后续判断。")
            relative_left, relative_right = st.columns([1.1, 1.45], vertical_alignment="top")
            with relative_left:
                with st.container(border=True):
                    relative_metrics = st.columns(2)
                    relative_metrics[0].metric("相对全市场", f"{relative_snapshot['相对市场']:+.2f}%" if relative_snapshot["相对市场"] is not None else "—", border=True, delta_color="inverse")
                    relative_metrics[1].metric("相对同类", f"{relative_snapshot['相对同类']:+.2f}%" if relative_snapshot["相对同类"] is not None else "—", border=True, delta_color="inverse")
                    relative_metrics[0].metric("市场平均", f"{relative_snapshot['市场平均']:+.2f}%" if relative_snapshot["市场平均"] is not None else "—", border=True)
                    relative_metrics[1].metric("同类位置", f"前 {peer_top_percent:.0f}%" if relative_snapshot["同类位置"] is not None else "待补同类", border=True)
            with relative_right:
                comparison_rows = [{"对照": "当前个股", "涨跌幅": relative_snapshot["个股涨跌"]}]
                if relative_snapshot["市场平均"] is not None:
                    comparison_rows.append({"对照": "全市场平均", "涨跌幅": relative_snapshot["市场平均"]})
                if relative_snapshot["同类平均"] is not None:
                    comparison_rows.append({"对照": f"{peer_field}平均", "涨跌幅": relative_snapshot["同类平均"]})
                comparison_frame = pd.DataFrame(comparison_rows).sort_values("涨跌幅")
                with st.container(border=True):
                    comparison_chart = px.bar(comparison_frame, x="涨跌幅", y="对照", orientation="h", color="涨跌幅", color_continuous_scale="RdYlGn_r", color_continuous_midpoint=0)
                    comparison_chart.update_layout(height=220, margin=dict(t=8, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title="涨跌幅（%）", yaxis_title="")
                    st.plotly_chart(comparison_chart, width="stretch")
        filled_fields = [field for field in ("价格", "涨跌幅", "成交额", "行业", "细分行业", "换手率", "量比") if field in df.columns and str(value(field)) not in {"", "—", "nan"}]
        with st.container(border=True):
            st.subheader("研究结论", icon=":material/fact_check:")
            fact_parts = [f"当日涨跌 {change:+.2f}%" if pd.notna(change) else "缺少当日涨跌数据"]
            if relative_rank is not None:
                fact_parts.append(f"全市场相对位置约前 {market_top_percent:.0f}%")
            if peer_average is not None and pd.notna(change):
                fact_parts.append(f"较同类平均 {change - peer_average:+.2f}%")
            if peer_rank is not None:
                fact_parts.append(f"同类相对位置约前 {peer_top_percent:.0f}%")
            st.write("｜".join(fact_parts))
            st.caption(f"数据完整度：已覆盖 {len(filled_fields)}/7 项常用研究字段。该结论为导入快照的统计描述，不构成买卖建议。")

        st.subheader("盘后复盘要点", icon=":material/checklist:")
        review_rows = []
        if relative_snapshot["相对市场"] is not None:
            review_rows.append({
                "观察项": "市场相对强弱",
                "当前快照": f"{relative_snapshot['相对市场']:+.2f}%",
                "复盘核对": "确认强弱是否由所属行业扩散带动，还是个股独立表现。",
            })
        if relative_snapshot["相对同类"] is not None:
            review_rows.append({
                "观察项": "同类相对强弱",
                "当前快照": f"{relative_snapshot['相对同类']:+.2f}%",
                "复盘核对": "对照同类前排与后排个股，核对个股在行业内部的位置。",
            })
        if pd.notna(turnover):
            turnover_series = pd.to_numeric(df.get("换手率", pd.Series(dtype=float)), errors="coerce").dropna()
            turnover_note = "换手活跃度处于市场中间区间。"
            if not turnover_series.empty:
                turnover_rank = float((turnover_series <= turnover).mean() * 100)
                turnover_note = "关注量能是否与价格强弱同步。" if turnover_rank >= 75 else "量能低于市场多数样本，关注后续持续性。" if turnover_rank <= 25 else turnover_note
            review_rows.append({
                "观察项": "换手与量能",
                "当前快照": f"换手 {turnover:.2f}%",
                "复盘核对": turnover_note,
            })
        missing_core = [field for field in ("成交额", "换手率", "量比", "行业", "细分行业") if field not in df.columns or pd.isna(value(field, None))]
        review_rows.append({
            "观察项": "数据完整性",
            "当前快照": f"待补 {len(missing_core)} 项" if missing_core else "核心字段已覆盖",
            "复盘核对": f"补充 { '、'.join(missing_core) } 后可完善横向研究。" if missing_core else "可结合云图、行业轮动与资金回放继续核对。",
        })
        with st.container(border=True):
            table(pd.DataFrame(review_rows), width="stretch", hide_index=True)
            st.caption("复盘要点是基于导入收盘快照生成的核对清单，用于整理研究路径，不构成交易指令。")
    if peers.empty:
        peer_board.caption("当前导入快照中没有足够的同类股票，导入全市场数据后会自动显示。")
    else:
        ranking_cols = peer_board.columns([1.3, 1, 1], vertical_alignment="bottom")
        sort_options = [field for field in ("涨跌幅", "成交额", "换手率", "综合分")
                        if field in peers and pd.to_numeric(peers[field], errors="coerce").notna().any()]
        with ranking_cols[0]:
            peer_sort = st.selectbox("同业榜单排序", sort_options or ["涨跌幅"], key=prefix+"detail_peer_sort", persist_state="session")
        with ranking_cols[1]:
            peer_direction = st.segmented_control("排序方向", ["从高到低", "从低到高"], default="从高到低", key=prefix+"detail_peer_direction", persist_state="session")
        with ranking_cols[2]:
            peer_limit = st.selectbox("同业展示数量", [10, 30, 50, 100], index=1, key=prefix+"detail_peer_limit", persist_state="session")
        if peer_sort not in (sort_options or ["涨跌幅"]) or peer_direction not in ("从高到低","从低到高") or type(peer_limit) is not int or peer_limit not in (10,30,50,100):
            st.warning("同业榜单选项无效。")
            return
        ranked_peers = rank_peer_quotes(peers, peer_sort, ascending=peer_direction == "从低到高")
        peer_columns = [field for field in ("代码", "名称", "价格", "涨跌幅", "成交额", "换手率", "综合分") if field in peers.columns]
        peer_config = {
            "涨跌幅": st.column_config.NumberColumn("涨跌幅", format="%.2f%%"),
            "成交额": st.column_config.NumberColumn("成交额", format="compact"),
            "综合分": st.column_config.NumberColumn("综合分", format="%.0f"),
        }
        peer_left, peer_right = peer_board.columns([1.2, 1], vertical_alignment="top")
        with peer_left:
            st.caption(f"比较维度：{peer_field} · {value(peer_field)}｜样本 {len(peers):,} 只" + (f"｜相对同类约前 {peer_top_percent:.0f}%" if peer_rank is not None else ""))
            peer_table = ranked_peers.head(peer_limit)[peer_columns]
            table(_ashare_change_style(peer_table), column_config=peer_config, width="stretch", hide_index=True, height=430)
            download("导出当前同业榜单", quote_export(peer_table, data).to_csv(index=False).encode("utf-8-sig"),
                               f"{selected_code}_同业榜单.csv", "text/csv", key=prefix+"detail_peer_export")
            st.caption(f"当前显示 {len(peer_table)} / {len(peers)} 只同业；缺失值保留未知，不以零替代。")
            if {"代码", "名称"}.issubset(peer_table.columns):
                peer_choices = (peer_table["代码"].astype(str) + " · " + peer_table["名称"].fillna("未命名").astype(str)).tolist()
                selected_peer = st.selectbox("打开同业研究卡", peer_choices, key=prefix+"detail_peer_jump")
                st.button(
                    "切换到该同业", icon=":material/swap_horiz:", key=prefix+"detail_open_peer",
                    on_click=_open_peer_stock, args=(peer_choices,),
                )
        with peer_right:
            chart_frame = ranked_peers.dropna(subset=[peer_sort]).head(min(peer_limit, 15)).iloc[::-1]
            if not chart_frame.empty and "名称" in chart_frame.columns:
                chart_label = peer_sort
                if peer_sort == "成交额":
                    chart_frame = chart_frame.assign(成交额亿元=chart_frame[peer_sort] / 1e8)
                    chart_label = "成交额亿元"
                peer_chart = px.bar(chart_frame, x=chart_label, y="名称", orientation="h", color="涨跌幅", color_continuous_scale="RdYlGn_r", color_continuous_midpoint=0)
                peer_chart.update_layout(height=430, margin=dict(t=10, l=0, r=0, b=0), coloraxis_showscale=False, xaxis_title=chart_label, yaxis_title="")
                st.plotly_chart(peer_chart, width="stretch")

    export = quote_export(pd.DataFrame([row.to_dict()]), data)
    with detail_tabs[3]:
        st.subheader('原始快照字段', icon=':material/database:')
        audit_rows = []
        for field, item in row.items():
            missing = pd.isna(item) or str(item).strip() in {'', '--', '—', 'nan', 'None'}
            audit_rows.append({'字段': str(field), '快照值': '—' if missing else str(item),
                               '状态': '未提供' if missing else '已提供'})
        table(pd.DataFrame(audit_rows), hide_index=True, width='stretch', height=350, key=prefix+'detail_raw_fields')
        st.caption('仅列出当前导入记录；未提供字段不补造，也不据此认定公司基本面。')
        download("导出当前个股研究卡 CSV", export.to_csv(index=False, encoding="utf-8-sig"), f"{selected_code}_research_card.csv", "text/csv")

