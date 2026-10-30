import streamlit as st
import plotly.express as px
from pathlib import Path
from .calculations import calculate_market_score, market_regime, position_targets, calculate_position_status, market_breadth_metrics, market_close_summary, decision_alerts, compare_market_snapshots, portfolio_risk_summary
from .models import TradePlan, TradeRecord
from .storage import save_trade_plan, list_trade_plans, save_trade_record, list_trade_records, save_portfolio_snapshot, list_portfolio_snapshots, save_market_snapshot, list_market_snapshots, list_theme_snapshots

DB_PATH = str(Path(__file__).resolve().parent.parent / "decision.db")


def render_decision_dashboard(state):
    latest_portfolio = list_portfolio_snapshots(DB_PATH)
    render_decision_summary(state)
    st.title("个人决策驾驶舱")
    total = st.number_input("总资产", min_value=0.0, value=float(st.session_state.get("total_assets", 1_100_000)), step=10000.0)
    st.session_state["total_assets"] = total
    regime = market_regime(state.get("score", 3))
    targets = position_targets(total, regime["name"])
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("大盘阶段", regime["name"])
    c2.metric("建议总仓位", f"{regime['total_low']:.0%}–{regime['total_high']:.0%}")
    c3.metric("建议进攻上限", f"{regime['attack_max']:.0%}")
    c4.metric("最低现金", f"{regime['cash']:.0%}")
    st.info(f"对应总仓位金额约 {targets['total_low']:,.0f}–{targets['total_high']:,.0f} 元。")
    close = market_close_summary(state.get("data", {}).get("stocks"))
    if close.get("status") != "no_quote":
        st.subheader("收盘市场摘要")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("市场状态", close["status"])
        q2.metric("上涨家数", close["up"], f"上涨占比 {close['advance_ratio']:.1%}")
        q3.metric("下跌家数", close["down"])
        q4.metric("涨跌幅中位数", f"{close['median_pct']:+.2f}%")
        st.caption("摘要来自最近导入的全市场收盘数据，仅作辅助判断；阶段评分仍以你在市场阶段页确认的六项条件为准。")
    if latest_portfolio:
        latest = latest_portfolio[0]
        positions = latest.get("positions", [])
        actual_value = sum(float(item.get("当前市值", item.get("amount", 0)) or 0) for item in positions)
        actual_ratio = actual_value / total if total else 0.0
        d1, d2, d3 = st.columns(3)
        d1.metric("最近快照实际总仓", f"{actual_value:,.0f} 元", f"{actual_ratio:.1%}")
        d2.metric("距阶段下限", f"{actual_value - targets['total_low']:+,.0f} 元")
        d3.metric("快照日期", latest["trade_date"])
        if actual_value > targets["total_high"]:
            st.warning("最近快照显示实际总仓高于当前阶段参考上限，请在持仓页核对。")
        elif actual_value < targets["total_low"]:
            st.info("最近快照显示实际总仓低于当前阶段参考下限，是否调整需结合你的交易计划。")
        concentrated = []
        for item in positions:
            amount = float(item.get("当前市值", item.get("amount", 0)) or 0)
            ratio = amount / total if total else 0.0
            if ratio > 0.15:
                label = item.get("名称") or item.get("name") or item.get("代码") or item.get("code") or "未命名"
                concentrated.append((label, ratio))
        if concentrated:
            names = "、".join(f"{label} {ratio:.1%}" for label, ratio in concentrated)
            st.warning(f"单票集中度提示（超过 15%）：{names}。请结合单票止损线复核。")
        history_rows = []
        for snapshot in latest_portfolio[:30]:
            value = sum(float(item.get("当前市值", item.get("amount", 0)) or 0) for item in snapshot.get("positions", []))
            history_rows.append({"日期": snapshot["trade_date"], "实际总仓": value, "仓位比例": value / total if total else 0.0})
        if len(history_rows) > 1:
            st.subheader("历史仓位趋势")
            history_df = __import__("pandas").DataFrame(history_rows).sort_values("日期")
            st.line_chart(history_df.set_index("日期")["仓位比例"])
    else:
        st.caption("尚无持仓快照；在“持仓管理”中保存后，这里会自动显示实际仓位对比。")
    risk_summary = portfolio_risk_summary(positions, total) if latest_portfolio else None
    alerts = decision_alerts(actual_value if latest_portfolio else 0.0, total, targets, risk_summary, close)
    if alerts:
        st.subheader("决策提醒")
        for alert in alerts:
            st.warning(alert)
    export_rows = [{
        "记录日期": __import__("datetime").date.today().isoformat(),
        "大盘阶段": regime["name"],
        "评分": state.get("score", 0),
        "总资产": total,
        "目标总仓下限": targets["total_low"],
        "目标总仓上限": targets["total_high"],
        "建议进攻上限": targets["attack_max"],
        "最低现金比例": regime["cash"],
        "最近快照实际总仓": actual_value if latest_portfolio else None,
        "收盘市场状态": close.get("status"),
        "上涨家数": close.get("up"),
        "下跌家数": close.get("down"),
        "上涨占比": close.get("advance_ratio"),
        "涨跌幅中位数": close.get("median_pct"),
        **{f"判断_{key}": value for key, value in state.get("scores", {}).items()},
    }]
    report_df = __import__("pandas").DataFrame(export_rows)
    st.download_button("导出收盘决策报告 CSV", report_df.to_csv(index=False, encoding="utf-8-sig"), "close_decision_report.csv", "text/csv")
    st.caption("本工具用于整理信息和执行纪律，不自动下单。")


def render_decision_summary(state):
    total = float(st.session_state.get("total_assets", 1100000.0))
    regime = market_regime(state.get("score", 3))
    targets = position_targets(total, regime["name"])
    mid_total = (targets["total_low"] + targets["total_high"]) / 2
    attack_ratio = regime["attack_max"]
    defense_ratio = max(0.0, mid_total / total - attack_ratio) if total else 0.0
    attack = total * attack_ratio
    defense = total * defense_ratio
    cash = total - mid_total
    st.subheader("���װ�һ�������ο�")
    a, b, c = st.columns(3)
    a.metric("�����м�ֵ", f"{mid_total:,.0f} Ԫ", f"{mid_total / total:.1%}" if total else "-")
    b.metric("���� / ����", f"{attack:,.0f} / {defense:,.0f} Ԫ", "4�� + 2��")
    c.metric("�����ֵ", f"{cash:,.0f} Ԫ", f"{cash / total:.1%}" if total else "-")
    st.dataframe([
        {"����": "����", "�ο���λ����": f"{attack:,.0f} Ԫ", "�ܲ�����": f"{attack_ratio:.0%}"},
        {"����": "����", "�ο���λ����": f"{defense:,.0f} Ԫ", "�ܲ�����": f"{defense_ratio:.0%}"},
        {"����": "�ֽ�", "�ο���λ����": f"{cash:,.0f} Ԫ", "�ܲ�����": f"{cash / total:.0%}" if total else "-"},
    ], use_container_width=True, hide_index=True)


def render_decision_summary(state):
    total = float(st.session_state.get("total_assets", 1_100_000.0))
    regime = market_regime(state.get("score", 3))
    targets = position_targets(total, regime["name"])
    mid_total = (targets["total_low"] + targets["total_high"]) / 2
    attack_ratio = min(regime["attack_max"], mid_total / total) if total else 0.0
    defense_ratio = max(0.0, mid_total / total - attack_ratio) if total else 0.0
    cash_ratio = max(0.0, 1 - mid_total / total) if total else 0.0
    st.subheader("\u9636\u6bb5\u76ee\u6807\u4ed3\u4f4d\u53c2\u8003")
    a, b, c = st.columns(3)
    a.metric("\u76ee\u6807\u603b\u4ed3\u4f4d\uff08\u533a\u95f4\u4e2d\u503c\uff09", f"{mid_total:,.0f} \u5143", f"{mid_total / total:.1%}" if total else "-")
    b.metric("\u8fdb\u653b / \u9632\u5b88\u4ed3", f"{total * attack_ratio:,.0f} / {total * defense_ratio:,.0f} \u5143", "4 \u4e2a\u8fdb\u653b\u4f4d + 2 \u4e2a\u9632\u5b88\u4f4d")
    c.metric("\u73b0\u91d1\u53c2\u8003", f"{total * cash_ratio:,.0f} \u5143", f"{cash_ratio:.1%}" if total else "-")
    rows = [
        {"\u8d44\u4ea7\u7c7b\u522b": "\u8fdb\u653b\u4ed3", "\u53c2\u8003\u91d1\u989d": f"{total * attack_ratio:,.0f} \u5143", "\u5360\u603b\u8d44\u4ea7": f"{attack_ratio:.1%}"},
        {"\u8d44\u4ea7\u7c7b\u522b": "\u9632\u5b88\u4ed3", "\u53c2\u8003\u91d1\u989d": f"{total * defense_ratio:,.0f} \u5143", "\u5360\u603b\u8d44\u4ea7": f"{defense_ratio:.1%}"},
        {"\u8d44\u4ea7\u7c7b\u522b": "\u73b0\u91d1", "\u53c2\u8003\u91d1\u989d": f"{total * cash_ratio:,.0f} \u5143", "\u5360\u603b\u8d44\u4ea7": f"{cash_ratio:.1%}"},
    ]
    from .personal_visual import render_allocation, render_market_context
    render_allocation(total, attack_ratio, defense_ratio, cash_ratio)
    render_market_context(state)


def render_market_score(state):
    pool = state.get("data", {}).get("research_pool")
    if pool is not None and "\u6da8\u8dcc\u5e45" in pool.columns:
        changes = pool["\u6da8\u8dcc\u5e45"].dropna()
        if len(changes):
            breadth = st.columns(4)
            breadth[0].metric("\u6709\u6da8\u8dcc\u5e45\u6570\u636e", f"{len(changes):,} / {len(pool):,}")
            breadth[1].metric("\u4e0a\u6da8 / \u4e0b\u8dcc", f"{int((changes > 0).sum()):,} / {int((changes < 0).sum()):,}")
            breadth[2].metric("\u5e73\u76d8", f"{int((changes == 0).sum()):,}")
            breadth[3].metric("\u6da8\u8dcc\u5e45\u4e2d\u4f4d\u6570", f"{changes.median():+.2f}%")
            st.caption("\u5e02\u573a\u5e7f\u5ea6\u53d6\u81ea\u6700\u8fd1\u4e00\u6b21\u540c\u82b1\u987a\u5168\u5e02\u573a TXT \u5bfc\u51fa\uff1b\u505c\u724c/\u7f3a\u503c\u4e0d\u8ba1\u5165\uff0c\u4e0d\u4f1a\u81ea\u52a8\u5237\u65b0")
    st.title("大盘阶段评分")
    labels = ["沪深300趋势","中证1000趋势","成交额","涨跌家数","涨跌停结构","科技强弱"]
    values = [st.checkbox(x, value=bool(state.get("scores", {}).get(x, 0))) for x in labels]
    score = calculate_market_score(values)
    state["score"] = score
    state["scores"] = dict(zip(labels, values))
    st.success(f"当前评分：{score}/6，阶段：{market_regime(score)['name']}")


def render_my_stock_pool(state):
    st.title("我的股票池")
    st.dataframe(state["data"]["stocks"], use_container_width=True, hide_index=True)


def render_portfolio_summary(state):
    total = float(st.session_state.get("total_assets", 1100000.0))
    regime = market_regime(state.get("score", 3))
    actuals = [float(st.session_state.get(f"portfolio_{i}", 0.0)) for i in range(6)]
    actual_total = sum(actuals)
    ratio = actual_total / total if total else 0.0
    st.caption(f"\u5f53\u524d\u9636\u6bb5\uff1a{regime['name']}\uff0c\u5f55\u5165\u603b\u4ed3\u4f4d\uff1a{ratio:.1%}\uff0c\u5efa\u8bae\u533a\u95f4\uff1a{regime['total_low']:.0%}\u2013{regime['total_high']:.0%}")
    if ratio > regime["total_high"]:
        st.error("\u5f53\u524d\u603b\u4ed3\u4f4d\u8d85\u8fc7\u9636\u6bb5\u4e0a\u9650\uff0c\u8bf7\u4f18\u5148\u964d\u4f4e\u66dd\u5149\u3002")
    elif ratio < regime["total_low"]:
        st.warning("\u5f53\u524d\u603b\u4ed3\u4f4d\u4f4e\u4e8e\u9636\u6bb5\u4e0b\u9650\uff0c\u662f\u5426\u52a0\u4ed3\u9700\u7ed3\u5408\u8ba1\u5212\u3002")
    else:
        st.success("\u5f53\u524d\u603b\u4ed3\u4f4d\u5728\u5efa\u8bae\u533a\u95f4\u5185\u3002")


def render_portfolio(state):
    st.title("持仓管理")
    total = st.number_input("总资产", min_value=0.0, value=1_100_000.0, step=10000.0)
    slots = [("进攻1",.15,.25),("进攻2",.12,.20),("进攻3",.08,.15),("进攻4",.05,.10),("防守1",.10,.15),("防守2",.05,.10)]
    rows=[]
    for name, low, high in slots:
        st.text_input(f"{name} stock code / name", key=f"stock_{name}", placeholder="e.g. 688008 澜起科技")
        actual=st.number_input(f"{name} 实际市值", min_value=0.0, step=1000.0, key=name)
        rows.append({"槽位":name,"实际金额":actual,"实际比例":actual/total if total else 0,"目标区间":f"{low:.0%}–{high:.0%}","状态":calculate_position_status(actual,total,low,high)})
    for index, row in enumerate(rows):
        slot_name = list(row.values())[0]
        row["stock"] = st.session_state.get(f"stock_{slot_name}", "")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    chart_rows = [{"slot": list(row.values())[0], "amount": float(list(row.values())[1])} for row in rows if float(list(row.values())[1]) > 0]
    if chart_rows:
        st.plotly_chart(px.pie(chart_rows, names="slot", values="amount", hole=0.45, title="Portfolio allocation"), use_container_width=True)
    total_ratio = sum(list(row.values())[1] for row in rows) / total if total else 0.0
    st.caption(f"Current portfolio ratio: {total_ratio:.1%}. Compare it with the regime range above before adjusting exposure.")
    stop_rate = st.number_input("Single-stock stop-loss rate", min_value=0.01, max_value=0.50, value=0.20, step=0.01)
    risk_amount = sum(list(row.values())[1] * stop_rate for row in rows)
    r1, r2 = st.columns(2)
    r1.metric("Estimated 20% stop-loss risk", f"{risk_amount:,.0f} 元")
    r2.metric("Risk / total assets", f"{risk_amount / total:.1%}" if total else "-")
    if st.button("Save portfolio snapshot", key="save_portfolio_snapshot"):
        values = [{"slot": list(row.values())[0], "stock": row.get("stock", ""), "amount": float(list(row.values())[1])} for row in rows]
        save_portfolio_snapshot(DB_PATH, str(__import__('datetime').date.today()), values)
        st.success("Portfolio snapshot saved.")
    snapshots = list_portfolio_snapshots(DB_PATH)
    if snapshots:
        st.caption(f"Saved snapshots: {len(snapshots)}; latest: {snapshots[0]['trade_date']}")
        history = []
        for snap in snapshots[:10]:
            amount = sum(float(item.get("amount", 0)) for item in snap["positions"])
            history.append({"date": snap["trade_date"], "total_amount": amount, "portfolio_ratio": amount / total if total else 0.0})
        st.dataframe(history, use_container_width=True, hide_index=True)
        history_csv = __import__('pandas').DataFrame(history).to_csv(index=False, encoding="utf-8-sig")
        st.download_button("Download snapshot history CSV", history_csv, "portfolio_snapshots.csv", "text/csv")
    return
    total_actual = sum(row["ʵ�ʽ��"] for row in rows)
    total_ratio = total_actual / total if total else 0.0
    st.caption(f"��¼�ܲ��䣺{total_ratio:.1%}�� ���ڵ�ǰģ�ͽ׶ν����ܲ��䣺20%�C95%��")


def render_trade_journal(db_path):
    st.title("交易计划与复盘")
    st.caption("把交易前逻辑、失效条件和事后结果放在同一条记录里，定期检查自己是否按框架执行。")
    review = st.text_area("复盘备注", key="review_notes", placeholder="记录实际结果、是否按计划执行、偏差原因和下次改进……")
    with st.form("trade_plan"):
        plan_date=st.date_input("计划日期", value=__import__('datetime').date.today())
        code=st.text_input("股票代码")
        name=st.text_input("股票名称")
        horizon=st.selectbox("周期", ["中线", "短线"])
        thesis=st.text_area("交易逻辑")
        invalidation=st.text_area("失效条件")
        weight=st.number_input("计划仓位", min_value=0.0, max_value=1.0, value=0.1, step=0.01)
        stop=st.number_input("计划止损价", min_value=0.0, value=0.0, step=0.01)
        take=st.number_input("计划止盈价", min_value=0.0, value=0.0, step=0.01)
        submitted=st.form_submit_button("保存计划")
        if submitted:
            plan = TradePlan(str(plan_date), code, name, horizon, thesis, invalidation, weight, stop or None, take or None, review)
            save_trade_plan(db_path, plan)
            st.success(f"已保存 {code} 的交易计划。")
    with st.expander("录入实际成交", expanded=False):
        with st.form("trade_record"):
            record_date = st.date_input("成交日期", value=__import__('datetime').date.today(), key="record_date")
            record_code = st.text_input("成交股票代码", key="record_code")
            record_name = st.text_input("成交股票名称", key="record_name")
            action = st.selectbox("方向", ["买入", "卖出"], key="record_action")
            price = st.number_input("成交价", min_value=0.0, step=0.01, key="record_price")
            quantity = st.number_input("数量", min_value=0, step=100, key="record_quantity")
            fee = st.number_input("手续费", min_value=0.0, step=0.01, key="record_fee")
            note = st.text_input("成交备注", key="record_note")
            if st.form_submit_button("保存成交记录"):
                if record_code and price > 0 and quantity > 0:
                    save_trade_record(db_path, TradeRecord(str(record_date), record_code, record_name, action, price, int(quantity), fee, note))
                    st.success("成交记录已保存。")
                else:
                    st.warning("请至少填写代码、成交价和数量。")
    records = list_trade_records(db_path)
    if records:
        record_df = __import__('pandas').DataFrame([r.__dict__ for r in records])
        record_df["成交金额"] = record_df["price"] * record_df["quantity"]
        buy_amount = record_df.loc[record_df["action"] == "买入", "成交金额"].sum()
        sell_amount = record_df.loc[record_df["action"] == "卖出", "成交金额"].sum()
        a, b, c = st.columns(3)
        a.metric("成交笔数", len(record_df))
        b.metric("累计买入", f"{buy_amount:,.0f} 元")
        c.metric("累计卖出", f"{sell_amount:,.0f} 元")
        d, e = st.columns(2)
        d.metric("净资金流", f"{sell_amount - buy_amount:,.0f} 元")
        e.metric("累计手续费", f"{record_df['fee'].sum():,.2f} 元")
        st.subheader("实际成交记录")
        st.dataframe(record_df, use_container_width=True, hide_index=True)
        st.download_button("导出成交记录 CSV", record_df.to_csv(index=False, encoding="utf-8-sig"), "trade_records.csv", "text/csv")
    plans = list_trade_plans(db_path)
    if plans:
        st.subheader("历史计划")
        plan_df = __import__('pandas').DataFrame([p.__dict__ for p in plans])
        m1, m2, m3 = st.columns(3)
        m1.metric("计划记录", len(plan_df))
        m2.metric("涉及股票", plan_df["code"].replace("", __import__('pandas').NA).nunique())
        m3.metric("平均计划仓位", f"{plan_df['planned_weight'].mean():.1%}")
        reviewed = plan_df["review"].fillna("").astype(str).str.strip().ne("")
        r1, r2 = st.columns(2)
        r1.metric("已复盘", int(reviewed.sum()))
        r2.metric("待复盘", int((~reviewed).sum()))
        st.progress(float(reviewed.mean()) if len(reviewed) else 0.0, text=f"复盘完成度：{reviewed.mean():.0%}")
        horizon_filter = st.selectbox("复盘筛选周期", ["全部", "短线", "中线"])
        shown = plan_df if horizon_filter == "全部" else plan_df[plan_df["horizon"] == horizon_filter]
        review_filter = st.selectbox("复盘状态", ["全部", "待复盘", "已复盘"])
        if review_filter == "待复盘":
            shown = shown[shown["review"].fillna("").astype(str).str.strip().eq("")]
        elif review_filter == "已复盘":
            shown = shown[shown["review"].fillna("").astype(str).str.strip().ne("")]
        date_filter = st.selectbox("时间范围", ["全部", "最近 7 天", "最近 30 天"])
        if date_filter != "全部":
            import datetime as _dt
            days = 7 if date_filter == "最近 7 天" else 30
            cutoff = _dt.date.today() - _dt.timedelta(days=days)
            dates = __import__('pandas').to_datetime(shown["trade_date"], errors="coerce").dt.date
            shown = shown[dates >= cutoff]
        shown = shown.assign(_待复盘=shown["review"].fillna("").astype(str).str.strip().eq("").map({True: 0, False: 1}))
        shown = shown.sort_values(["_待复盘", "trade_date"], ascending=[True, False]).drop(columns=["_待复盘"])
        st.dataframe(shown, use_container_width=True, hide_index=True)
        plans_csv = shown.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("导出复盘记录 CSV", plans_csv, "trade_journal.csv", "text/csv")


def render_my_stock_pool(state):
    st.title("\u6211\u7684\u80a1\u7968\u6c60")
    df = state["data"].get("research_pool", state["data"]["stocks"]).copy()
    df = df.loc[:, ~df.columns.duplicated()].copy()
    required = ["\u4ee3\u7801", "\u540d\u79f0"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        st.error("股票池缺少必要字段：" + "、".join(missing))
        return
    total_count = len(df)
    if "\u677f\u5757" in df.columns:
        board_count = int(df["\u677f\u5757"].nunique())
    else:
        board_count = 0
    known_quotes = int((df["\u4ef7\u683c"].fillna(0) > 0).sum()) if "\u4ef7\u683c" in df.columns else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("观察股票", total_count)
    m2.metric("板块分类", board_count)
    m3.metric("包含行情报价", known_quotes)
    if known_quotes == 0:
        st.info("当前导入文件提供的是股票代码/名称观察名单，没有可用的价格和涨跌幅字段；不要把空行情当作零涨跌。行情可继续从终端导出后再导入。")
    keyword = st.text_input("\u641c\u7d22\u4ee3\u7801\u6216\u540d\u79f0")
    sectors = ["\u5168\u90e8", *sorted(df["\u677f\u5757"].dropna().astype(str).unique())] if "\u677f\u5757" in df.columns else ["\u5168\u90e8"]
    sector = st.selectbox("\u4ea4\u6613\u6240\u677f\u5757\u7b5b\u9009", sectors)
    industry_col = "\u7ec6\u5206\u884c\u4e1a" if "\u7ec6\u5206\u884c\u4e1a" in df.columns else "\u884c\u4e1a" if "\u884c\u4e1a" in df.columns else None
    industries = ["\u5168\u90e8", *sorted(df[industry_col].dropna().astype(str).unique())] if industry_col else ["\u5168\u90e8"]
    industry = st.selectbox("\u884c\u4e1a / \u9898\u6750\u5206\u7c7b", industries)
    minimum_score = st.slider("\u6700\u4f4e\u7efc\u5408\u5206", 0, 100, 0)
    if keyword:
        mask = df["\u4ee3\u7801"].astype(str).str.contains(keyword, case=False, na=False) | df["\u540d\u79f0"].astype(str).str.contains(keyword, case=False, na=False)
        df = df[mask]
    if sector != "\u5168\u90e8" and "\u677f\u5757" in df.columns:
        df = df[df["\u677f\u5757"].astype(str) == sector]
    if industry != "\u5168\u90e8" and industry_col:
        df = df[df[industry_col].astype(str) == industry]
    if "\u7efc\u5408\u5206" in df.columns:
        df = df[df["\u7efc\u5408\u5206"] >= minimum_score]
    st.caption(f"\u5f53\u524d\u80a1\u7968\u6c60 {len(df)} \u53ea\uff0c\u4ec5\u4f5c\u7814\u7a76\u89c2\u5bdf\uff0c\u4e0d\u81ea\u52a8\u4ea4\u6613")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Download filtered stock pool", df.to_csv(index=False, encoding="utf-8-sig"), "filtered_stock_pool.csv", "text/csv")


def render_report_center():
    st.title("报告中心")
    st.caption("统一查看市场、主题、仓位、成交和复盘记录。")
    report_days = st.selectbox("报告范围", ["最近记录", "最近 7 天", "最近 30 天", "全部历史"])
    market = list_market_snapshots(DB_PATH, limit=20)
    themes = list_theme_snapshots(DB_PATH, limit=20)
    portfolios = list_portfolio_snapshots(DB_PATH)[:20]
    plans = list_trade_plans(DB_PATH)
    records = list_trade_records(DB_PATH)
    if report_days != "全部历史":
        import datetime as _dt
        cutoff = _dt.date.today() - _dt.timedelta(days=7 if report_days == "最近 7 天" else 30 if report_days == "最近 30 天" else 3650)
        market = [x for x in market if str(x.get("trade_date", "")) >= cutoff.isoformat()]
        themes = [x for x in themes if str(x.get("trade_date", "")) >= cutoff.isoformat()]
        portfolios = [x for x in portfolios if str(x.get("trade_date", "")) >= cutoff.isoformat()]
        plans = [x for x in plans if str(x.trade_date) >= cutoff.isoformat()]
        records = [x for x in records if str(x.trade_date) >= cutoff.isoformat()]
    a, b, c, d = st.columns(4)
    a.metric("市场快照", len(market)); b.metric("主题快照", len(themes)); c.metric("仓位快照", len(portfolios)); d.metric("成交记录", len(records))
    if market:
        market_df = __import__("pandas").DataFrame(market)
        st.subheader("市场快照"); st.dataframe(market_df, use_container_width=True, hide_index=True)
        st.download_button("导出市场报告", market_df.to_csv(index=False, encoding="utf-8-sig"), "market_report.csv", "text/csv")
    if themes:
        theme_df = __import__("pandas").DataFrame(themes)
        st.subheader("主题快照"); st.dataframe(theme_df, use_container_width=True, hide_index=True)
        st.download_button("导出主题报告", theme_df.to_csv(index=False, encoding="utf-8-sig"), "theme_report.csv", "text/csv")
    if portfolios:
        portfolio_df = __import__("pandas").DataFrame([{"日期": p["trade_date"], "持仓数量": len(p.get("positions", [])), "总市值": sum(float(x.get("当前市值", x.get("amount", 0)) or 0) for x in p.get("positions", []))} for p in portfolios])
        st.subheader("仓位快照"); st.dataframe(portfolio_df, use_container_width=True, hide_index=True)
        st.download_button("导出仓位报告", portfolio_df.to_csv(index=False, encoding="utf-8-sig"), "portfolio_report.csv", "text/csv")
    if plans:
        plan_df = __import__("pandas").DataFrame([p.__dict__ for p in plans])
        done = plan_df["review"].fillna("").astype(str).str.strip().ne("")
        st.subheader("复盘进度"); st.progress(float(done.mean()), text=f"已复盘 {int(done.sum())}/{len(done)} 条")
        st.download_button("导出复盘报告", plan_df.to_csv(index=False, encoding="utf-8-sig"), "review_report.csv", "text/csv")
    if not any((market, themes, portfolios, plans, records)):
        st.info("当前时间范围没有可用报告记录。")
    else:
        combined = []
        for label, rows in (("市场", market), ("主题", themes), ("仓位", portfolios), ("计划", [p.__dict__ for p in plans]), ("成交", [r.__dict__ for r in records])):
            for row in rows:
                combined.append({"报告类型": label, **{str(k): v for k, v in row.items()}})
        combined_df = __import__("pandas").DataFrame(combined).fillna("")
        st.download_button("导出综合报告 CSV", combined_df.to_csv(index=False, encoding="utf-8-sig"), "research_report_all.csv", "text/csv")


def render_personal_page(page, data):
    if page == "赛博交易舱":
        from .cyber_desk import render_cyber_desk

        render_cyber_desk(data)
        return
    if "decision_state" not in st.session_state:
        latest = list_market_snapshots(DB_PATH, limit=1)
        restored = latest[0] if latest else {}
        st.session_state["decision_state"] = {
            "score": int(restored.get("score", 3)),
            "scores": restored.get("scores", {}),
            "data": data,
        }
    state = st.session_state["decision_state"]
    state["data"] = data
    if page == "报告中心": render_report_center()
    elif page == "决策驾驶舱": render_decision_dashboard(state)
    elif page == "我的交易模型": render_market_score(state)
    elif page == "持仓管理": render_portfolio(state)
    elif page == "\u6211\u7684\u80a1\u7968\u6c60": render_my_stock_pool(state)
    else: render_trade_journal(DB_PATH)


def render_market_score(state):
    import datetime
    import pandas as pd
    st.title("\U0001f4ca\u5927\u76d8\u9636\u6bb5\u5224\u65ad")
    snapshots = list_market_snapshots(DB_PATH)
    breadth_data = market_breadth_metrics(state.get("data", {}).get("research_pool"))
    if breadth_data:
        st.subheader("\u5168\u5e02\u573a\u5e7f\u5ea6\uff08\u6700\u8fd1\u5bfc\u5165\u5feb\u7167\uff09")
        cells = st.columns(6)
        cells[0].metric("\u6709\u6548\u6da8\u8dcc\u6570", f"{breadth_data['valid']:,} / {breadth_data['total']:,}")
        cells[1].metric("\u4e0a\u6da8 / \u4e0b\u8dcc", f"{breadth_data['up']:,} / {breadth_data['down']:,}")
        cells[2].metric("\u5e73\u76d8", f"{breadth_data['flat']:,}")
        cells[3].metric("\u6da8\u8dcc\u4e2d\u4f4d\u6570", f"{breadth_data['median_pct']:+.2f}%")
        cells[4].metric("\u5bfc\u5165\u6210\u4ea4\u989d\u5408\u8ba1", f"{breadth_data['amount_sum']/1e8:,.0f}\u4ebf" if breadth_data.get("amount_sum") is not None else "\u65e0\u6570\u636e")
        breadth_label = {"broad_advance": "\u5bbd\u5e45\u666e\u6da8", "broad_decline": "\u5bbd\u5e45\u666e\u8dcc", "mixed": "\u6da8\u8dcc\u5206\u5316"}[breadth_data["breadth_read"]]
        cells[5].metric("\u5e02\u573a\u5e7f\u5ea6\u89e3\u8bfb", breadth_label, f"\u4e0a\u6da8\u5360 {breadth_data['advance_ratio']:.0%}")
        st.caption(f"\u8fd9\u53ea\u662f\u6570\u636e\u63d0\u793a\uff08\u666e\u6da8\uff1a\u4e0a\u6da8\u5360\u6bd4\u226560%\u4e14\u4e2d\u4f4d\u6da8\u5e45\u4e3a\u6b63\uff1b\u666e\u8dcc\uff1a\u5360\u6bd4\u226440%\u4e14\u4e2d\u4f4d\u6da8\u5e45\u4e3a\u8d1f\uff09\uff0c\u4e0d\u4f1a\u4ee3\u66ff\u4f60\u6253\u5206\u3002\u6210\u4ea4\u989d\u4e3a {breadth_data.get('amount_rows', 0):,} \u884c\u5408\u8ba1\uff0c\u975e\u4ea4\u6613\u6240\u7edf\u8ba1\u53e3\u5f84\uff1b\u6570\u636e\u4ee5\u6700\u8fd1\u5bfc\u5165\u5feb\u7167\u4e3a\u51c6\u3002")
    labels = ["\u6caa\u6df1300\u8d8b\u52bf", "\u4e2d\u8bc11000\u8d8b\u52bf", "\u4e24\u5e02\u6210\u4ea4\u989d", "\u6da8\u8dcc\u5bb6\u6570", "\u6da8\u8dcc\u505c\u7ed3\u6784", "\u79d1\u6280\u5f3a\u5f31"]
    st.subheader("\u516d\u9879\u4eba\u5de5\u5224\u5206\u5bf9\u5e94\u7684\u4ed3\u4f4d\u53c2\u8003")
    regime_guide = pd.DataFrame([
        {"\u5f97\u5206": "0\u20131 / 6", "\u5927\u76d8\u9636\u6bb5": "\u7cfb\u7edf\u98ce\u9669", "\u76ee\u6807\u603b\u4ed3": "20%\u201330%", "\u8fdb\u653b\u4ed3\u4e0a\u9650": "10%", "\u73b0\u91d1\u5e95\u7ebf": "70%"},
        {"\u5f97\u5206": "2 / 6", "\u5927\u76d8\u9636\u6bb5": "\u9707\u8361\u5e02", "\u76ee\u6807\u603b\u4ed3": "40%\u201350%", "\u8fdb\u653b\u4ed3\u4e0a\u9650": "30%", "\u73b0\u91d1\u5e95\u7ebf": "50%"},
        {"\u5f97\u5206": "3\u20134 / 6", "\u5927\u76d8\u9636\u6bb5": "\u4fee\u590d\u9636\u6bb5", "\u76ee\u6807\u603b\u4ed3": "60%\u201370%", "\u8fdb\u653b\u4ed3\u4e0a\u9650": "50%", "\u73b0\u91d1\u5e95\u7ebf": "30%"},
        {"\u5f97\u5206": "5\u20136 / 6", "\u5927\u76d8\u9636\u6bb5": "\u8d8b\u52bf\u9636\u6bb5", "\u76ee\u6807\u603b\u4ed3": "80%\u201395%", "\u8fdb\u653b\u4ed3\u4e0a\u9650": "65%", "\u73b0\u91d1\u5e95\u7ebf": "5%"},
    ])
    stage_cards_placeholder = st.container()
    st.caption("\u6bcf\u4e2a\u52fe\u9009\u8ba1 1 \u5206\uff1b\u5e7f\u5ea6\u4ec5\u63d0\u793a\uff0c\u9700\u4f60\u81ea\u884c\u5224\u65ad\u540e\u624b\u52a8\u52fe\u9009\u3002\u4ed3\u4f4d\u6863\u4f4d\u662f\u53c2\u8003\u89c4\u5219\uff0c\u4e0d\u662f\u4ea4\u6613\u6307\u4ee4\u3002")
    today = datetime.date.today()
    trade_date = st.date_input("\u76d8\u9762\u8bb0\u5f55\u65e5\u671f", value=today, key="market_stage_date")
    saved_today = next((item for item in snapshots if item["trade_date"] == trade_date.isoformat()), {})
    if trade_date != today:
        st.info("\u4f60\u9009\u4e86\u5386\u53f2\u65e5\u671f\uff1b\u9876\u90e8\u5e02\u573a\u5e7f\u5ea6\u4ecd\u662f\u6700\u8fd1\u5bfc\u5165\u5feb\u7167\uff0c\u4e0d\u4f1a\u9519\u8bef\u5199\u5165\u8be5\u65e5\u6863\u6848\u3002")
    with st.form("market_stage_snapshot"):
        c1, c2, c3 = st.columns(3)
        hs300 = c1.number_input("\u6caa\u6df1300\u6da8\u8dcc%", value=float(saved_today.get("hs300_pct", 0.0)), step=0.1, format="%.2f")
        csi1000 = c2.number_input("\u4e2d\u8bc11000\u6da8\u8dcc%", value=float(saved_today.get("csi1000_pct", 0.0)), step=0.1, format="%.2f")
        tech = c3.number_input("\u79d1\u6280\u677f\u5757\u76f8\u5bf9\u5f3a\u5f31%", value=float(saved_today.get("tech_relative_pct", 0.0)), step=0.1, format="%.2f", help="\u586b\u79d1\u6280\u677f\u5757\u76f8\u5bf9\u5927\u76d8\u7684\u6da8\u8dcc\u5e45\uff0c\u53ef\u6309\u6982\u5ff5\u6307\u6570\u624b\u52a8\u8bb0\u5f55")
        defaults = saved_today.get("scores", state.get("scores", {}))
        values = [st.checkbox(label, value=bool(defaults.get(label, False)), key=f"stage_factor_{i}") for i, label in enumerate(labels)]
        rationale = st.text_area("\u4eca\u65e5\u5224\u65ad\u4f9d\u636e / \u4e3b\u8981\u50ac\u5316", value=saved_today.get("rationale", ""), max_chars=1000)
        invalidation = st.text_area("\u4ec0\u4e48\u60c5\u51b5\u4f1a\u8ba9\u6211\u63a8\u7ffb\u8fd9\u4e2a\u5224\u65ad", value=saved_today.get("invalidation", ""), max_chars=1000)
        save = st.form_submit_button("\u4fdd\u5b58\u4eca\u65e5\u5224\u65ad\uff08\u540c\u65e5\u8986\u76d6\u66f4\u65b0\uff09")
    score = calculate_market_score(values)
    regime = market_regime(score)
    state["score"], state["scores"] = score, dict(zip(labels, values))
    from .personal_visual import render_stage_cards
    with stage_cards_placeholder:
        render_stage_cards(score)
    st.success(f"\u5f53\u524d\u6253\u5206 {score}/6 | \u9636\u6bb5\uff1a{regime['name']} | \u5efa\u8bae\u4ed3\u4f4d {regime['total_low']:.0%}\u2013{regime['total_high']:.0%} | \u73b0\u91d1\u5e95\u7ebf {regime['cash']:.0%}")
    st.caption("\u8d8b\u52bf\u52fe\u9009\u662f\u4f60\u7684\u4eba\u5de5\u5224\u65ad\uff1b\u6bcf\u5929\u6536\u76d8\u540e\u586b\u5199\u5e76\u63d0\u4ea4\u5f52\u6863\u3002\u4ec5\u7528\u4e8e\u51b3\u7b56\u8f85\u52a9\uff0c\u4e0d\u4f1a\u81ea\u52a8\u4e0b\u5355\u3002")
    prior = next((item for item in snapshots if item["trade_date"] < trade_date.isoformat()), None)
    if prior:
        current_breadth = breadth_data if trade_date == today else saved_today.get("breadth", {})
        comparison = compare_market_snapshots(
            {"score": score, "stage": regime["name"], "breadth": current_breadth or {}},
            prior,
            float(st.session_state.get("total_assets", 1_100_000.0)),
        )
        st.subheader(f"\u4e0e\u4e0a\u4e00\u6761\u5df2\u5b58\u8bb0\u5f55\u5bf9\u6bd4\uff08{prior['trade_date']}\uff09")
        change_cells = st.columns(4)
        score_change = comparison["score_delta"]
        change_cells[0].metric("\u5224\u5206\u53d8\u5316", f"{score}/6", f"{score_change:+d} \u5206")
        change_cells[1].metric("\u5927\u76d8\u9636\u6bb5", regime["name"], "\u5207\u6362\u9636\u6bb5" if comparison["stage_changed"] else "\u9636\u6bb5\u672a\u53d8")
        change_cells[2].metric("\u5efa\u8bae\u603b\u4ed3\u91d1\u989d", f"{comparison['position_low']:,.0f}\u2013{comparison['position_high']:,.0f} \u5143")
        change_cells[3].metric("\u4ed3\u4f4d\u533a\u95f4\u53d8\u5316", f"{comparison['position_low_delta']:+,.0f}\u2013{comparison['position_high_delta']:+,.0f} \u5143")
        if comparison["advance_ratio_delta"] is not None:
            st.caption(f"\u5168\u5e02\u573a\u4e0a\u6da8\u5360\u6bd4\u53d8\u5316\uff1a{comparison['advance_ratio_delta']:+.1%}\uff08\u4ee5\u5df2\u4fdd\u5b58\u5feb\u7167\u4e3a\u51c6\uff09")
    if save:
        breadth_snapshot = breadth_data if trade_date == today else saved_today.get("breadth", {})
        payload = {"score": score, "stage": regime["name"], "scores": dict(zip(labels, values)), "hs300_pct": hs300, "csi1000_pct": csi1000, "tech_relative_pct": tech, "breadth": breadth_snapshot or {}, "rationale": rationale, "invalidation": invalidation}
        save_market_snapshot(DB_PATH, trade_date.isoformat(), payload)
        st.success("\u9636\u6bb5\u5feb\u7167\u5df2\u4fdd\u5b58\uff0c\u540c\u4e00\u65e5\u91cd\u65b0\u63d0\u4ea4\u4f1a\u66f4\u65b0\u8bb0\u5f55\u3002")
    if snapshots:
        st.subheader("\u8fd1\u671f\u9636\u6bb5\u590d\u76d8")
        history = pd.DataFrame([{ "\u65e5\u671f": x["trade_date"], "\u5f97\u5206": x.get("score"), "\u9636\u6bb5": x.get("stage"), "\u6caa\u6df1300%": x.get("hs300_pct"), "\u4e2d\u8bc11000%": x.get("csi1000_pct"), "\u79d1\u6280\u76f8\u5bf9%": x.get("tech_relative_pct"), "\u4e0a\u6da8\u5360\u6bd4": x.get("breadth", {}).get("advance_ratio"), "\u5e7f\u5ea6\u5224\u8bfb": {"broad_advance": "\u666e\u6da8", "broad_decline": "\u666e\u8dcc", "mixed": "\u5206\u5316"}.get(x.get("breadth", {}).get("breadth_read")), "\u6da8\u80a1": x.get("breadth", {}).get("up"), "\u8dcc\u80a1": x.get("breadth", {}).get("down"), "\u5224\u65ad\u4f9d\u636e": x.get("rationale", ""), "\u63a8\u7ffb\u6761\u4ef6": x.get("invalidation", "")} for x in snapshots])
        st.dataframe(history, use_container_width=True, hide_index=True)
        st.download_button("\u4e0b\u8f7d\u9636\u6bb5\u590d\u76d8 CSV", history.to_csv(index=False, encoding="utf-8-sig"), "market_stage_history.csv", "text/csv")
        chart = history.dropna(subset=["\u5f97\u5206"]).sort_values("\u65e5\u671f")
        if not chart.empty:
            st.plotly_chart(px.line(chart, x="\u65e5\u671f", y="\u5f97\u5206", markers=True, title="\u9636\u6bb5\u4fe1\u53f7\u5386\u53f2"), use_container_width=True)


def render_portfolio(state):
    import datetime
    st.title("\U0001f4bc\u6301\u4ed3\u7ba1\u7406")
    total_default = float(st.session_state.get("total_assets", 1_100_000.0))
    total = st.number_input("\u603b\u8d44\u4ea7\uff08\u5143\uff09", min_value=0.0, value=total_default, step=10000.0, key="total_assets")
    stage = market_regime(state.get("score", 3))
    slots = [
        ("\u8fdb\u653b\u4ed31", .15, .25), ("\u8fdb\u653b\u4ed32", .12, .20),
        ("\u8fdb\u653b\u4ed33", .08, .15), ("\u8fdb\u653b\u4ed34", .05, .10),
        ("\u9632\u5b881", .10, .15), ("\u9632\u5b882", .05, .10),
    ]
    st.caption(f"\u5927\u76d8\u9636\u6bb5\uff1a{stage['name']}\uff5c\u53c2\u8003\u603b\u4ed3 {stage['total_low']:.0%}\u2013{stage['total_high']:.0%}\uff08{total*stage['total_low']:,.0f}\u2013{total*stage['total_high']:,.0f} \u5143\uff09")
    rows = []
    chart_slot = st.container()
    st.caption('点击对应仓位编辑；红点表示实际占比，蓝色带表示参考区间。')
    for index, (slot, low, high) in enumerate(slots):
        if index % 3 == 0:
            slot_columns = st.columns(3)
        with slot_columns[index % 3].popover(f"编辑 {slot}", width='stretch'):
            st.caption(f'参考 {low:.0%}–{high:.0%}，不是买入指令')
            a = b = c = st
            stock = a.text_input("\u80a1\u7968\u4ee3\u7801 / \u540d\u79f0", key=f"holding_stock_{index}", placeholder="留空表示暂未配置")
            amount = b.number_input("\u5f53\u524d\u5e02\u503c\uff08\u5143\uff09", min_value=0.0, step=1000.0, key=f"holding_amount_{index}")
            stop_pct_input = c.number_input("\u5355\u80a1\u6b62\u635f\u8ddd\u79bb\uff08%\uff0c0\u4e3a\u672a\u8bbe\uff09", min_value=0.0, max_value=100.0, step=1.0, key=f"holding_stop_{index}")
            reason = st.text_input("\u6b62\u635f\u4f9d\u636e / \u5931\u6548\u6761\u4ef6", key=f"holding_stop_reason_{index}", placeholder="\u4f8b\uff1a\u903b\u8f91\u7834\u574f / \u652f\u6491\u4f4d\u5931\u5b88")
        actual_ratio = amount / total if total else 0.0
        stop_pct = stop_pct_input / 100 if stop_pct_input > 0 else None
        rows.append({
            "\u69fd\u4f4d": slot, "\u80a1\u7968": stock or "\u2014", "\u5f53\u524d\u5e02\u503c": amount,
            "\u5b9e\u9645\u5360\u6bd4": actual_ratio, "\u76ee\u6807\u533a\u95f4": f"{low:.0%}\u2013{high:.0%}",
            "\u4ed3\u4f4d\u72b6\u6001": calculate_position_status(amount, total, low, high),
            "\u6b62\u635f\u8ddd\u79bb": stop_pct, "\u6b62\u635f\u4f9d\u636e": reason,
            "\u98ce\u9669\u91d1\u989d": amount * stop_pct if stop_pct is not None else None,
        })
    summary = portfolio_risk_summary([{"amount": row["\u5f53\u524d\u5e02\u503c"], "stop_pct": row["\u6b62\u635f\u8ddd\u79bb"]} for row in rows], total)
    from .personal_visual import slot_range_figure
    with chart_slot:
        st.subheader('六个仓位 · 实际与参考')
        st.plotly_chart(slot_range_figure(rows, total), width='stretch', key='personal_slot_ranges')
    kpis = st.columns(4)
    kpis[0].metric("\u6301\u4ed3\u5e02\u503c", f"{summary['market_value']:,.0f} \u5143", f"\u603b\u8d44\u4ea7 {summary['portfolio_ratio']:.1%}")
    kpis[1].metric("\u9636\u6bb5\u76ee\u6807\u4ed3\u4f4d", f"{stage['total_low']:.0%}\u2013{stage['total_high']:.0%}")
    kpis[2].metric("\u5df2\u8bbe\u6b62\u635f\u7684\u4f30\u7b97\u98ce\u9669", f"{summary['estimated_loss']:,.0f} \u5143", f"\u603b\u8d44\u4ea7 {summary['risk_ratio']:.2%}" if total else "\u8d44\u4ea7\u4e3a0")
    kpis[3].metric("\u6b62\u635f\u5f85\u5b8c\u5584", f"{summary['unprotected_positions']} \u53ea")
    if total and summary["portfolio_ratio"] > stage["total_high"]:
        st.error("\u5f53\u524d\u603b\u4ed3\u9ad8\u4e8e\u9636\u6bb5\u53c2\u8003\u4e0a\u9650\uff1b\u8bf7\u6838\u5bf9\u66b4\u9732\uff0c\u8fd9\u4e0d\u662f\u81ea\u52a8\u51cf\u4ed3\u6307\u4ee4\u3002")
    elif total and summary['market_value'] > 0 and summary["portfolio_ratio"] < stage["total_low"]:
        st.info("\u5f53\u524d\u603b\u4ed3\u4f4e\u4e8e\u9636\u6bb5\u53c2\u8003\u533a\u95f4\uff1b\u4e0d\u81ea\u52a8\u63d0\u793a\u4e70\u5165\uff0c\u9700\u7ed3\u5408\u8ba1\u5212\u3002")
    if summary["unprotected_positions"]:
        st.warning(f"\u6709 {summary['unprotected_positions']} \u53ea\u5df2\u5f55\u5165\u7684\u6301\u4ed3\u672a\u8bbe\u5355\u80a1\u6b62\u635f\u8ddd\u79bb\uff1b\u4e0a\u65b9\u98ce\u9669\u91d1\u989d\u4e0d\u5305\u542b\u8fd9\u4e9b\u6301\u4ed3\uff0c\u4e0d\u80fd\u89e3\u8bfb\u4e3a\u7ec4\u5408\u6700\u5927\u98ce\u9669\u3002")
    if not summary['market_value']:
        st.caption('尚未录入持仓，暂不判定低配。')
    st.caption('单槽参考不要求同时填满；仍受阶段总仓与进攻上限约束。')
    chart_rows = [{"\u4ed3\u4f4d": row["\u69fd\u4f4d"], "\u5e02\u503c": row["\u5f53\u524d\u5e02\u503c"]} for row in rows if row["\u5f53\u524d\u5e02\u503c"] > 0]
    if chart_rows:
        with st.expander('查看实际持仓分布', expanded=False):
            st.plotly_chart(px.bar(chart_rows, x='市值', y='仓位', orientation='h', title='实际持仓金额（不含现金）'), width='stretch')
    if st.button("\u4fdd\u5b58\u6301\u4ed3\u5feb\u7167", key="save_portfolio_snapshot"):
        save_portfolio_snapshot(DB_PATH, datetime.date.today().isoformat(), rows)
        st.success("\u6301\u4ed3\u5feb\u7167\u5df2\u4fdd\u5b58\uff08\u540c\u65e5\u53ef\u91cd\u590d\u7559\u5b58\u4f5c\u5386\u53f2\u7248\u672c\uff09")
    snapshots = list_portfolio_snapshots(DB_PATH)
    if snapshots:
        history = []
        for snap in snapshots[:20]:
            value = sum(float(item.get("\u5f53\u524d\u5e02\u503c", item.get("amount", 0)) or 0) for item in snap["positions"])
            history.append({"\u65e5\u671f": snap["trade_date"], "\u6301\u4ed3\u5e02\u503c": value, "\u8d44\u4ea7\u5360\u6bd4": value / total if total else 0})
        with st.expander('持仓历史与下载', expanded=False):
            st.dataframe(history, width='stretch', hide_index=True)
            st.download_button("\u4e0b\u8f7d\u6301\u4ed3\u5386\u53f2 CSV", __import__("pandas").DataFrame(history).to_csv(index=False, encoding="utf-8-sig"), "portfolio_snapshots.csv", "text/csv")
