"""Original snapshot candidate workbench with injected data and isolated state."""
from math import isfinite
import pandas as pd
import streamlit as st
from ...calculations import stock_snapshot_history,stock_top_percent
from ...technology_cards import classify_technology,price_range,TECHNOLOGY_TAXONOMY
from ..scanner_model import filter_candidates,candidate_review_report,quote_detail_values,_display,select_market_group_column
from ..components import public_table
from ..contracts import STOCK_FIELDS


def render(snapshot,capabilities,navigation):
    history=snapshot.optional.get("history")
    data=dict(stocks=snapshot.stocks,import_date=snapshot.metadata["date"],stock_quote_source="imported",
        market_history=history.frame if history is not None else pd.DataFrame())
    st.caption(snapshot.metadata["source"])
    render_frame(data,capabilities,navigation,navigation.namespace+"_")

def render_frame(data,capabilities,navigation,prefix=''):

    state=navigation.state
    def _select_candidate(label):
        state[prefix+"scanner_stock_jump"] = label

    def _reset_scanner_filters():
        for key in (prefix+"scanner_query", prefix+"scanner_sort_field", prefix+"scanner_group", prefix+"scanner_min_change", prefix+"scanner_min_amount", prefix+"scanner_limit", prefix+"scanner_stock_jump", prefix+"scanner_page", prefix+"scanner_preset", prefix+"scanner_market", prefix+"scanner_min_score", prefix+"scanner_max_risk", prefix+"scanner_technology", prefix+"scanner_technology_layer"):
            state.pop(key, None)

    def _apply_scanner_preset(sort_options):
        preset = state.get(prefix+"scanner_preset", "自定义")
        options = {"强势动量": (3.0, 1.0, "涨跌幅"), "成交活跃": (-30.0, 2.0, "成交额"), "全景复盘": (-30.0, 0.0, "涨跌幅")}
        if preset not in options:
            return
        change, amount, sort_field = options[preset]
        state[prefix+"scanner_min_change"] = change
        state[prefix+"scanner_min_amount"] = amount
        state[prefix+"scanner_sort_field"] = sort_field if sort_field in sort_options else (sort_options[0] if sort_options else "默认顺序")
        state[prefix+"scanner_page"] = 1

    def _sync_candidate_page(labels):
        selected = state.get(prefix+"scanner_stock_jump")
        if selected in labels:
            state[prefix+"scanner_page"] = labels.index(selected) // 10 + 1

    def table(frame,**kwargs):
        return public_table(frame,(*STOCK_FIELDS,"科技方向","科技细分","分类依据","综合分","风险分"),capabilities,**kwargs)
    def download(*args,**kwargs):
        if capabilities.download: return st.download_button(*args,**kwargs)
    st.subheader("盘中选股 · 快照研究工作台", icon=":material/filter_alt:")
    stocks = data.get("stocks", pd.DataFrame()).copy()
    if stocks.empty or not {"代码", "名称"}.issubset(stocks):
        st.warning("请先导入包含代码、名称和行情的市场快照。")
        return
    stocks["代码"] = stocks["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    stocks = classify_technology(stocks)
    origin = "导入行情快照" if data.get("stock_quote_source") == "imported" else "演示行情 · 非真实报价"
    valid_changes = pd.to_numeric(stocks.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").notna().sum()
    st.caption(f"{origin}｜交易日：{data.get('import_date') or '未提供'}｜样本 {len(stocks):,} 只 · 有效涨跌 {valid_changes:,} 只；非实时扫描。")
    group_field = select_market_group_column(stocks)
    group_options = sorted(stocks[group_field].dropna().astype(str).unique()) if group_field in stocks else []
    sort_options = [field for field in ("涨跌幅", "成交额", "换手率", "综合分", "风险分")
                    if field in stocks and pd.to_numeric(stocks[field], errors="coerce").notna().any()]
    preset_col, search_col, sort_col = st.columns([1.8, 1.8, 1], vertical_alignment="bottom")
    with preset_col:
        st.segmented_control("研究预设", ["自定义", "强势动量", "成交活跃", "全景复盘"], default="自定义", key=prefix+"scanner_preset", persist_state="session", on_change=_apply_scanner_preset, args=(sort_options,), help="仅调整涨幅、成交额门槛和排序；不生成预测胜率或模型评分。")
    with search_col:
        query = st.text_input("搜索股票代码 / 名称 / 题材", key=prefix+"scanner_query", placeholder="例如 PCB、688008", persist_state="session")
    with sort_col:
        sort_field = st.selectbox("候选排序依据", sort_options or ["默认顺序"], key=prefix+"scanner_sort_field", persist_state="session")

    summary = st.container()
    controls, candidates, preview = st.columns([0.85, 1.7, 1.3], vertical_alignment="top")
    with controls:
        with st.container(border=True):
            st.subheader("筛选条件", icon=":material/tune:")
            with st.expander('高级筛选 · 上市市场与原始行业', expanded=False):
                market = st.selectbox("市场范围", ["全部市场", "沪市主板", "深市主板", "创业板", "科创板", "北交所"], key=prefix+"scanner_market", persist_state="session")
                st.caption("上市市场不是科技分类；仅在需要限制科创板、创业板等样本时使用。")
                market_stocks = filter_candidates(stocks, market=market, minimum_change=float('-inf'))
                group_options = sorted(market_stocks[group_field].dropna().astype(str).unique()) if group_field in market_stocks else []
                if state.get(prefix+'scanner_group', '全部') not in ['全部', *group_options]:
                    state[prefix+'scanner_group'] = '全部'
                group = st.selectbox("行业 / 产业链筛选", ["全部", *group_options], key=prefix+"scanner_group", persist_state="session")
            technology = st.selectbox("科技研究方向", ['全部', *TECHNOLOGY_TAXONOMY], key=prefix+'scanner_technology', persist_state='session')
            technology_scope = market_stocks if technology == '全部' else market_stocks.loc[market_stocks['科技方向'].eq(technology)]
            # Actual imported subindustries remain visible; reserved research nodes do not invent members.
            actual_layers = sorted(technology_scope.loc[technology_scope['科技方向'].ne('其他 / 未分类'), '科技细分'].unique())
            layers = ['全部', *dict.fromkeys([*TECHNOLOGY_TAXONOMY.get(technology, []), *actual_layers])]
            if state.get(prefix+'scanner_technology_layer', '全部') not in layers:
                state[prefix+'scanner_technology_layer'] = '全部'
            technology_layer = st.selectbox('科技细分 / 产业链环节', layers, key=prefix+'scanner_technology_layer', persist_state='session')
            st.caption('研究导航不是官方行业库。PCB 为参考名单；其余是导入字段初筛，业务归属尚待逐股核验。光通信不等于 CPO，软件不等于 AI 应用，医药不等于创新药。')
            minimum_change = st.slider("最低涨幅（%）", -30.0, 30.0, 0.0, 0.5, key=prefix+"scanner_min_change", persist_state="session")
            minimum_amount = st.number_input("最低成交额（亿元）", min_value=0.0, value=0.0, step=0.5, key=prefix+"scanner_min_amount", persist_state="session")
            minimum_score = maximum_risk = None
            if "综合分" in sort_options:
                minimum_score = st.number_input("最低综合分（导入值）", value=0.0, step=5.0, key=prefix+"scanner_min_score", persist_state="session")
            if "风险分" in sort_options:
                imported_max_risk = float(pd.to_numeric(stocks["风险分"], errors="coerce").max())
                maximum_risk = st.number_input("最高风险分（导入值）", value=imported_max_risk, step=5.0, key=prefix+"scanner_max_risk", persist_state="session")
            display_limit = st.selectbox("候选上限", [20, 50, 100, 200], index=1, key=prefix+"scanner_limit", persist_state="session")
            st.button("重置筛选", icon=":material/restart_alt:", key=prefix+"scanner_reset_filters", on_click=_reset_scanner_filters, width="stretch")
            st.caption("风险分由低到高排列，其他字段由高到低排列；缺失成交额不满足正金额门槛。")
            st.subheader("排序维度", icon=":material/analytics:")
            for field in sort_options:
                available = pd.to_numeric(stocks[field], errors="coerce").notna().sum()
                st.caption(f"{field} · 有效 {available:,}/{len(stocks):,}")
            if "综合分" not in sort_options:
                st.caption("未提供综合评分，当前采用单项行情排序。")
            st.caption('模型权重：尚未接入可核验的评分公式；不将单项排序包装成综合模型或涨停概率。')

    if (sort_field not in (sort_options or ["默认顺序"]) or market not in ("全部市场","沪市主板","深市主板","创业板","科创板","北交所")
            or group not in ["全部",*group_options] or technology not in ["全部",*TECHNOLOGY_TAXONOMY] or technology_layer not in layers
            or display_limit not in (20,50,100,200) or not isfinite(float(minimum_change)) or not -30<=minimum_change<=30
            or not isfinite(float(minimum_amount)) or minimum_amount<0):
        st.warning("候选筛选无效。")
        return
    result = filter_candidates(stocks, query, group_field, group, minimum_change,
                               minimum_amount * 1e8, sort_field, sort_field == "风险分", market=market, minimum_score=minimum_score, maximum_risk=maximum_risk)
    if technology != '全部':
        result = result.loc[result['科技方向'].eq(technology)]
    if technology_layer != '全部':
        result = result.loc[result['科技细分'].eq(technology_layer)]
    visible = result.head(display_limit)
    with summary:
        changes = pd.to_numeric(result.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
        scores = pd.to_numeric(result.get("综合分", pd.Series(dtype=float)), errors="coerce").dropna()
        risks = pd.to_numeric(result.get("风险分", pd.Series(dtype=float)), errors="coerce").dropna()
        with st.container(horizontal=True):
            st.metric("入选候选", f"{len(result):,}", border=True)
            st.metric("最高综合分", f"{scores.max():.0f}" if not scores.empty else "未提供", border=True)
            st.metric("平均风险分", f"{risks.mean():.0f}" if not risks.empty else "未提供", border=True)
            st.metric("平均涨跌", f"{changes.mean():+.2f}%" if not changes.empty else "—", border=True)
    with candidates:
        st.subheader("候选榜单", icon=":material/leaderboard:")
        st.caption(f"符合条件 {len(result):,} 只 · 展示 {len(visible):,} 只 · 按{sort_field}排序")
        if visible.empty:
            st.info("没有匹配的候选。当前方向 / 环节可能尚缺归属名单，或被其他筛选条件排除；不代表该方向没有上市公司。")
        else:
            labels = (visible["代码"] + " · " + visible["名称"].fillna("未命名").astype(str)).tolist()
            if state.get(prefix+"scanner_stock_jump") not in labels:
                state[prefix+"scanner_stock_jump"] = labels[0]
            selected = st.selectbox("选择一只候选股继续研究", labels, key=prefix+"scanner_stock_jump", on_change=_sync_candidate_page, args=(labels,), persist_state="session")
            if selected not in labels:
                st.warning("候选选择无效。")
                return
            page_count = (len(visible) + 9) // 10
            if state.get(prefix+"scanner_page", 1) > page_count:
                state[prefix+"scanner_page"] = 1
            page = st.selectbox("候选页", list(range(1, page_count + 1)), key=prefix+"scanner_page", format_func=lambda number: f"第 {number} / {page_count} 页", persist_state="session")
            if type(page) is not int or not 1<=page<=page_count:
                st.warning("候选页码无效。")
                return
            page_start = (page - 1) * 10
            with st.container(height=740, border=False):
                for position, (_, row) in enumerate(visible.iloc[page_start:page_start + 10].iterrows(), start=page_start):
                    label = labels[position]
                    with st.container(border=True, gap="xsmall"):
                        title, quote = st.columns([2, 1])
                        with title:
                            st.button(label, key=prefix+f"scanner_candidate_{position}", width="stretch",
                                      type="primary" if selected == label else "secondary",
                                      on_click=_select_candidate, args=(label,))
                            st.caption(f"{row['科技方向']} · {row['科技细分']}" if row['科技方向'] != '其他 / 未分类' else str(row.get(group_field, "未分类")))
                        with quote:
                            st.metric("最新价", _display(row, "价格"), _display(row, "涨跌幅", percent=True), delta_color="inverse")
                        interval = price_range(row)
                        if interval is not None:
                            low, high, position_in_range = interval
                            st.progress(position_in_range, text=f'当日价格区间 {low:.2f} — {high:.2f} · 收盘位置 {position_in_range:.0%}（非分时）')
                        else:
                            st.caption('当日价格区间：高低价缺失或不一致，暂不绘制。')
                        st.table(pd.DataFrame([
                            {'指标': '成交额 / 换手率', '数值': f"{_display(row, '成交额', money=True)} / {_display(row, '换手率')}%"},
                            {'指标': '总市值 / 流通市值', '数值': f"{_display(row, '总市值', money=True)} / {_display(row, '流通市值', money=True)}"},
                            {'指标': '量比 / 综合分（导入值）', '数值': f"{_display(row, '量比')} / {_display(row, '综合分')}"},
                        ]), hide_index=True, border='horizontal', width='stretch')
                        st.caption('当日分时 / 均线 / MACD：尚无对应分钟及历史日线数据。')
                        tags = row.get("标签", "")
                        if pd.notna(tags) and str(tags).strip():
                            st.caption(str(tags))
            selected_row = visible.iloc[labels.index(selected)]
    with preview:
        with st.container(border=True):
            st.subheader("候选行情卡", icon=":material/query_stats:")
            if visible.empty:
                st.caption("选择候选后显示行情、归属与历史快照。")
            else:
                st.subheader(f"{selected_row['名称']} · {selected_row['代码']}")
                st.metric("最新价", _display(selected_row, "价格"), _display(selected_row, "涨跌幅", percent=True), delta_color="inverse")
                st.table(quote_detail_values(selected_row), border="horizontal", width="stretch")
                facts = st.columns(2)
                with facts[0]:
                    st.metric("成交额", _display(selected_row, "成交额", money=True))
                    st.metric("换手率", _display(selected_row, "换手率"))
                with facts[1]:
                    st.metric("量比", _display(selected_row, "量比"))
                    st.metric("流通市值", _display(selected_row, "流通市值", money=True))
                st.caption(f"归属：{selected_row.get(group_field, '未分类')}")
                st.caption(f"科技归属：{selected_row['科技方向']} → {selected_row['科技细分']}")
                st.caption(f"分类依据：{selected_row['分类依据']}")
                download("导出当前个股快照", selected_row.to_frame().T.assign(快照日期=data.get("import_date") or "未提供").to_csv(index=False).encode("utf-8-sig"), f"候选快照_{selected_row['代码']}.csv", "text/csv", key=prefix+"scanner_export_selected")
                with st.expander("市场相对位置", expanded=True):
                    for field in ("涨跌幅", "成交额", "换手率", "量比"):
                        if field not in stocks:
                            continue
                        top_percent = stock_top_percent(selected_row.get(field), stocks[field])
                        if top_percent is not None:
                            st.progress(max(0.0, 1 - top_percent / 100), text=f"{field} · 市场前 {top_percent:.1f}%")
                history = stock_snapshot_history(data.get("market_history", pd.DataFrame()), str(selected_row["代码"]), through_date=data.get("import_date"))
                if len(history) >= 2 and history["价格"].notna().sum() >= 2:
                    st.caption("已保存收盘价格")
                    st.line_chart(history.set_index("交易日")["价格"], height=150)
                else:
                    st.caption("历史快照不足，暂不绘制价格轨迹。")
                st.subheader("收盘候选研究路径", icon=":material/travel_explore:")
                def open_selected(detail=False):
                    label=state.get(prefix+"scanner_stock_jump")
                    if label not in labels: return
                    row=visible.iloc[labels.index(label)]
                    code=str(row["代码"])
                    group=str(row.get(group_field,""))
                    parent=str(row.get("行业",group)) if group_field=="细分行业" else group
                    if detail:
                        navigation.open_stock(code,set(stocks["代码"]),group,parent)
                    else:
                        pairs={(str(item.get("行业",item.get(group_field,""))),str(item.get(group_field,"")))
                            if group_field=="细分行业" else (str(item.get(group_field,"")),str(item.get(group_field,"")))
                            for _,item in stocks.iterrows()}
                        navigation.focus_sector(group_field,group,pairs,parent=parent)
                st.button("打开个股详情",key=prefix+"scanner_open_detail",icon=":material/open_in_new:",width="stretch",on_click=open_selected,args=(True,))
                target_group=str(selected_row.get(group_field,""))
                if target_group:
                    st.button("在大盘云图定位行业",key=prefix+"scanner_open_terminal",icon=":material/account_tree:",width="stretch",
                        on_click=open_selected,disabled=group_field not in ("行业","细分行业","板块"))
    with st.expander("候选明细与导出", expanded=False):
        table(visible, width="stretch", hide_index=True)
        download("导出当前候选清单 CSV", visible.to_csv(index=False).encode("utf-8-sig"), prefix+"scanner_candidates.csv", "text/csv")
        st.caption(f"符合条件共 {len(result):,} 只，候选卡展示前 {len(visible):,} 只；完整导出不受候选上限限制。")
        download("导出全部符合条件股票", result.assign(快照日期=data.get("import_date") or "未提供").to_csv(index=False).encode("utf-8-sig"), prefix+"scanner_full_candidates.csv", "text/csv", key=prefix+"scanner_export_full")
        report = candidate_review_report(
            date=data.get("import_date"), origin=origin, sample_count=len(stocks),
            matched_count=len(result), displayed_count=len(visible), query=query,
            market=market, group=group, minimum_change=minimum_change,
            minimum_amount=minimum_amount * 1e8, sort_field=sort_field,
            minimum_score=minimum_score, maximum_risk=maximum_risk,
        )
        report += f'\n科技研究方向：{technology}\n科技细分 / 环节：{technology_layer}'
        st.text(report)
        download("导出筛选口径与复盘说明", report.encode("utf-8-sig"),
                           prefix+"scanner_review_context.txt", "text/plain", key=prefix+"scanner_export_context")

