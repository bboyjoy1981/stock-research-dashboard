import streamlit as st
import datetime as dt
from pathlib import Path
from src.demo_data import load_demo_market
from src.ui import configure_page, render_sidebar, render_market_workspace_toolbar
from src.pages_public import render_public_page
from src.pages_personal import render_personal_page
from src.importers import read_tabular_upload, validate_stock_pool, save_research_upload, load_latest_research, load_research_history, stock_pool_template, normalize_stock_columns, load_capital_replay, available_quote_snapshot_dates, latest_quote_snapshot, select_research_snapshot
from src.data_sources import source_status
from src.feishu_notifier import (
    build_market_test_message,
    load_notifier_config,
    send_text_notification,
)

from src.importers import import_quality_report, infer_import_date

PAGES = ["决策驾驶舱", "大盘云图", "板块资金流向", "指数分析", "概念排行", "盘中选股", "板块热力图", "产业链分层", "热点舆情", "个股详情", "数据导入", "我的交易模型", "持仓管理", "交易计划与复盘"]


PAGES.append("\u6211\u7684\u80a1\u7968\u6c60")
PAGES.append("\u62a5\u544a\u4e2d\u5fc3")
PAGES.append("板块细分")
PAGES.append("赛博交易舱")


BASE_DIR = Path(__file__).resolve().parent
IMPORT_DIR = BASE_DIR / "data" / "imports"
CAPITAL_REPLAY_DIR = BASE_DIR / "data" / "capital_replay"


def main():
    configure_page()
    from src.login_entry import login_preview_requested, render_login_entry
    if login_preview_requested(st.query_params):
        render_login_entry()
        return
    data = load_demo_market()
    data["stock_quote_source"] = "demo"
    data["capital_replay"] = load_capital_replay(str(CAPITAL_REPLAY_DIR))
    data["capital_replay_dir"] = str(CAPITAL_REPLAY_DIR)
    imported = load_latest_research(str(IMPORT_DIR))
    data["market_history"] = load_research_history(str(IMPORT_DIR))
    data["import_date"] = None
    quote_frame, quote_date = latest_quote_snapshot(data["market_history"])
    if imported is not None and {"代码", "名称"}.issubset(imported.columns):
        research_pool = imported.copy()
        for col, default in [("板块", "未分类"), ("价格", 0.0), ("涨跌幅", 0.0), ("成交额", 0.0), ("标签", "")]:
            if col not in research_pool.columns:
                research_pool[col] = default
        data["research_pool"] = research_pool
    if quote_frame is not None:
        data["stocks"] = quote_frame
        data["stock_quote_source"] = "imported"
        data["import_date"] = quote_date
        data["source_notice"] = f"个股行情来自 {quote_date} 导入快照；指数和板块概览目前仍为演示数据。"
    elif imported is not None:
        data["source_notice"] = "已导入研究名单，但没有可用的涨跌幅行情快照；市场页面保留演示行情，不会把缺失数据误显示为零。"
    active = render_sidebar(PAGES)
    if active in {"市场总览", "大盘云图", "板块细分", "个股详情", "盘中选股"}:
        replay_dates = available_quote_snapshot_dates(data["market_history"])
        if replay_dates:
            replay_options = ["当前快照", *reversed(replay_dates)]
            if st.session_state.get("market_replay_date") not in replay_options:
                st.session_state["market_replay_date"] = "当前快照"
            selected_date = st.sidebar.selectbox(
                "盘后快照交易日", replay_options, key="market_replay_date",
                persist_state="session",
                help="市场总览、云图、个股详情和候选榜单共用此日期；当前快照采用最近交易日覆盖最完整的行情文件。",
            )
            if selected_date != "当前快照":
                data = select_research_snapshot(data, selected_date)
    from src.index_snapshot import load_index_snapshot
    data['index_snapshot'] = load_index_snapshot(BASE_DIR / 'data' / 'indices', data.get('import_date'))
    from src.close_limits import load_close_snapshot
    data['close_limit_snapshot'] = load_close_snapshot(BASE_DIR / 'data' / 'close_limits', data.get('import_date'))
    if active in {"市场总览", "大盘云图", "个股详情", "板块资金流向", "指数分析", "概念排行", "盘中选股", "板块热力图", "产业链分层", "热点舆情"}:
        render_market_workspace_toolbar(active, data)
    snapshot_date = data.get("import_date")
    if snapshot_date:
        st.sidebar.caption(f"当前快照：{snapshot_date}")
        try:
            age = (dt.date.today() - dt.date.fromisoformat(snapshot_date)).days
            if age > 3:
                st.sidebar.caption(f":orange[快照距今 {age} 天，非当前行情。]")
        except ValueError:
            pass
    with st.sidebar.expander("导入数据状态", expanded=False):
        st.caption(f"研究名单：{len(imported):,} 行" if imported is not None else "尚未导入研究名单")
        st.caption(data.get("source_notice", "当前为演示数据，请先导入收盘快照。"))
        st.caption("历史日期用于复盘；查看当日市场请重新导入当天收盘数据。")
    with st.sidebar.expander("数据源接入", expanded=False):
        status = source_status()
        st.caption("当前行情以导入文件/演示数据为主")
        st.write(f"Tushare Pro：{status['Tushare Pro']}")
        st.caption(status["说明"])
        st.info("接入方式：在服务器环境变量中配置 TUSHARE_TOKEN，重启后即可调用日线接口。")
        st.divider()
        notifier_config = load_notifier_config(secrets=st.secrets)
        st.caption(f"飞书通知：{notifier_config.safe_status}")
        st.caption("仅手动测试发送；未配置时不会产生外发请求。")
        if st.button("发送飞书测试通知", key="send_feishu_test_notification"):
            notification = send_text_notification(
                notifier_config,
                build_market_test_message(data.get("import_date"), dt.datetime.now()),
            )
            if notification.ok:
                st.success("飞书测试通知已发送。")
            else:
                st.info(notification.message)
    st.session_state.setdefault("total_assets", 1_100_000.0)
    if active in {"市场总览", "板块细分"}:
        render_public_page(active, data)
        return
    if active in {"大盘云图", "板块资金流向", "指数分析", "概念排行", "盘中选股", "板块热力图", "产业链分层", "热点舆情", "个股详情"}:
        render_public_page(active, data)
    elif active == "数据导入":
        st.title("数据导入")
        import_history = []
        for saved_file in sorted(IMPORT_DIR.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
            import_history.append({
                "文件": saved_file.name,
                "大小": f"{saved_file.stat().st_size / 1024:.1f} KB",
                "修改时间": __import__("datetime").datetime.fromtimestamp(saved_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "当前使用": "是" if not import_history else "否",
            })
        if import_history:
            st.subheader("已保存的导入快照")
            st.dataframe(import_history, use_container_width=True, hide_index=True)
            st.download_button("导出导入历史清单 CSV", __import__("pandas").DataFrame(import_history).to_csv(index=False, encoding="utf-8-sig"), "import_history.csv", "text/csv")
            st.caption("系统默认读取最新修改的 CSV；原始文件不会被覆盖。")
        st.caption("导入研究数据前请先在同花顺导出 CSV 或 Excel；不会自动覆盖个人交易记录。")
        st.download_button("下载股票池模板", stock_pool_template().to_csv(index=False, encoding="utf-8-sig"), "股票池导入模板.csv", "text/csv")
        uploaded = st.file_uploader("上传股票池文件", type=["csv", "txt", "xlsx", "xls"])
        if uploaded:
            try:
                frame = read_tabular_upload(uploaded.getvalue(), uploaded.name)
                frame = normalize_stock_columns(frame)
                errors = validate_stock_pool(frame)
                if errors:
                    st.error("；".join(errors))
                else:
                    st.success(f"文件校验通过，共 {len(frame)} 行。")
                    quality = import_quality_report(frame)
                    q1, q2, q3 = st.columns(3)
                    q1.metric("\u53ef\u7528\u884c\u60c5\u884c", f"{quality['valid_quotes']:,} / {quality['rows']:,}")
                    q2.metric("\u6709\u6548\u8986\u76d6\u7387", f"{quality['valid_quotes'] / quality['rows']:.1%}" if quality["rows"] else "0%")
                    q3.metric("\u5b57\u6bb5\u72b6\u6001", "\u5b8c\u6574" if not quality["partial_fields"] and not quality["missing_fields"] else "\u90e8\u5206\u7f3a\u5931")
                    imported_date = infer_import_date(frame)
                    if imported_date:
                        st.caption(f"识别到交易日期：{imported_date}；保存后市场研究页面将优先使用这份快照。")
                    snapshot_day = st.date_input(
                        "行情交易日期（不是文件保存日期）",
                        value=dt.date.fromisoformat(imported_date) if imported_date else None,
                        max_value=dt.date.today(), key="upload_trade_date",
                        help="文件未包含日期时，请核对同花顺行情所属交易日后选择。",
                    )
                    st.caption("已完成字段标准化：代码、名称、板块、行业、价格、涨跌幅、成交额等字段会统一命名。")
                    if quality["missing_fields"]:
                        st.warning("\u6570\u636e\u4e2d\u7f3a\u5c11\uff1a" + "\u3001".join(quality["missing_fields"]) + "\uff1b\u76f8\u5173\u5224\u65ad\u4e0d\u4f1a\u81ea\u52a8\u4f30\u7b97\u3002")
                    elif quality["partial_fields"]:
                        st.info("\u90e8\u5206\u884c\u7f3a\u5c11\u6709\u6548\u503c\uff1a" + "\u3001".join(quality["partial_fields"]) + "\u3002")
                    st.dataframe(frame, use_container_width=True, hide_index=True)
                    if st.button("保存为研究数据", disabled=snapshot_day is None):
                        frame["交易日期"] = snapshot_day.isoformat()
                        path = save_research_upload(frame, str(IMPORT_DIR), "stock_pool")
                        st.session_state["market_replay_date"] = "当前快照"
                        st.success(f"已保存：{path}")
                    st.info("保存会生成带时间戳的新文件，不会覆盖原文件或个人交易记录。")
            except Exception as exc:
                st.error(str(exc))
    else:
        render_personal_page(active, data)


if __name__ == "__main__":
    main()
