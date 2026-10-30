"""Original stock snapshot comparison over supplied observations only."""
import pandas as pd
import streamlit as st
from ...snapshot_review import compare_saved_snapshots
from ..components import public_table


def render(history, code, capabilities, prefix=""):
    def table(frame,**kwargs):
        return public_table(frame,tuple(frame.columns),capabilities,**kwargs)
    def download(*args,**kwargs):
        if capabilities.download: return st.download_button(*args,**kwargs)
    if history.empty:
        return
    snapshots = history.rename(columns={"交易日": "快照日期"}).assign(代码=code)
    review = compare_saved_snapshots(snapshots)
    if review["stocks"].empty:
        return
    dates = sorted(snapshots["快照日期"].dropna().astype(str).loc[lambda values: values.lt(review["current_date"])].unique(), reverse=True)
    baseline = st.selectbox("个股对照交易日", dates, key=prefix+f"detail_compare_baseline_{code}", persist_state="session")
    review = compare_saved_snapshots(snapshots, baseline_date=baseline)
    row = review["stocks"].iloc[0]
    st.caption(f"快照对照：{review['baseline_date']} → {review['current_date']}")
    with st.container(horizontal=True):
        st.metric("保存日价格变化", f"{row['价格变化']:+.2f}%" if pd.notna(row['价格变化']) else "—", border=True)
        st.metric("当日涨幅变化", f"{row['涨跌幅变化']:+.2f} 个百分点" if pd.notna(row['涨跌幅变化']) else "—", border=True)
        st.metric("成交额倍数", f"{row['成交额倍数']:.2f} 倍" if pd.notna(row['成交额倍数']) else "—", border=True)
    st.caption("对照当前与选定保存日的快照；价格未复权，日期之间可能缺少交易日，不能据此还原完整区间走势。")
    details = pd.DataFrame([
        {"交易日": review["baseline_date"], "价格": row["价格_对照"], "当日涨跌幅": row["涨跌幅_对照"], "成交额": row["成交额_对照"]},
        {"交易日": review["current_date"], "价格": row["价格_当前"], "当日涨跌幅": row["涨跌幅_当前"], "成交额": row["成交额_当前"]},
    ])
    table(details, width="stretch", hide_index=True, column_config={
        "价格": st.column_config.NumberColumn(format="%.2f"),
        "当日涨跌幅": st.column_config.NumberColumn(format="%+.2f%%"),
        "成交额": st.column_config.NumberColumn(format="compact"),
    })
    export = review["stocks"].assign(当前交易日=review["current_date"], 对照交易日=baseline)
    download("导出个股快照对照", export.to_csv(index=False).encode("utf-8-sig"), f"个股对照_{code}_{review['current_date']}_{baseline}.csv", "text/csv", key=prefix+f"detail_compare_export_{code}")

