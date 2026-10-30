"""Compare observed snapshots on the same set of stock codes."""
import pandas as pd


def industry_snapshot_comparison(frame):
    """Aggregate common-stock observations, never mismatched turnover totals."""
    columns = ["行业", "共同样本", "涨幅有效样本", "平均涨幅变化", "走强比例", "成交额有效样本", "成交额覆盖率", "成交额倍数"]
    if frame.empty or "行业" not in frame:
        return pd.DataFrame(columns=columns)
    data = frame.copy()
    data["行业"] = data["行业"].fillna("未分类").astype(str).str.strip().replace("", "未分类")
    for field in ["涨跌幅变化", "成交额_当前", "成交额_对照"]:
        data[field] = pd.to_numeric(data.get(field, pd.Series(index=data.index, dtype=float)), errors="coerce")
    rows = []
    for industry, group in data.groupby("行业", sort=True):
        changes = group["涨跌幅变化"].dropna()
        amounts = group.loc[group["成交额_当前"].ge(0) & group["成交额_对照"].ge(0)].dropna(subset=["成交额_当前", "成交额_对照"])
        prior = amounts["成交额_对照"].sum()
        rows.append({"行业": industry, "共同样本": len(group), "涨幅有效样本": len(changes),
                     "平均涨幅变化": changes.mean(), "走强比例": changes.gt(0).mean() * 100 if len(changes) else float("nan"),
                     "成交额有效样本": len(amounts), "成交额覆盖率": len(amounts) / len(group) * 100,
                     "成交额倍数": amounts["成交额_当前"].sum() / prior if prior > 0 else float("nan")})
    return pd.DataFrame(rows, columns=columns)


def snapshot_change_distribution(frame):
    """Count observed percentage-point changes, without zero-filling missing values."""
    values = pd.to_numeric(frame.get("涨跌幅变化", pd.Series(dtype=float)), errors="coerce")
    labels = ["低于 -2", "-2 至 0（不含0）", "持平", "0 至 2（不含0）", "高于 +2", "缺失"]
    counts = [values.lt(-2).sum(), (values.ge(-2) & values.lt(0)).sum(), values.eq(0).sum(),
              (values.gt(0) & values.le(2)).sum(), values.gt(2).sum(), values.isna().sum()]
    return pd.DataFrame({"区间": labels, "股票数": counts})


def compare_saved_snapshots(history, through_date=None, baseline_date=None):
    empty = {"current_date": None, "baseline_date": None, "added": 0, "removed": 0, "current_count": 0, "baseline_count": 0, "stocks": pd.DataFrame()}
    if history is None or history.empty or not {"快照日期", "代码"}.issubset(history):
        return empty
    frame = history.copy()
    frame["快照日期"] = frame["快照日期"].fillna("").astype(str).str.strip()
    frame = frame.loc[frame["快照日期"].ne("")]
    if through_date:
        frame = frame.loc[frame["快照日期"].le(str(through_date))]
    dates = sorted(frame["快照日期"].unique())
    if len(dates) < 2:
        return empty
    current_date = dates[-1]
    baseline_date = str(baseline_date) if baseline_date else dates[-2]
    if baseline_date not in dates or baseline_date >= current_date:
        return empty
    frame["代码"] = frame["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    current = frame.loc[frame["快照日期"].eq(current_date)].drop_duplicates("代码", keep="last")
    previous = frame.loc[frame["快照日期"].eq(baseline_date)].drop_duplicates("代码", keep="last")
    current_codes, previous_codes = set(current["代码"]), set(previous["代码"])
    fields = ["代码", "名称", "价格", "涨跌幅", "成交额"]
    for snapshot in (current, previous):
        for field in fields[1:]:
            if field not in snapshot:
                snapshot[field] = "" if field == "名称" else float("nan")
            elif field != "名称":
                snapshot[field] = pd.to_numeric(snapshot[field], errors="coerce")
    merged = current[fields].merge(previous[fields], on="代码", how="inner", suffixes=("_当前", "_对照"))
    merged["名称"] = merged["名称_当前"].fillna(merged["名称_对照"])
    merged["涨跌幅变化"] = merged["涨跌幅_当前"] - merged["涨跌幅_对照"]
    valid_prices = merged["价格_当前"].gt(0) & merged["价格_对照"].gt(0)
    merged["价格变化"] = (merged["价格_当前"] / merged["价格_对照"] - 1).where(valid_prices) * 100
    merged["成交额倍数"] = (merged["成交额_当前"] / merged["成交额_对照"]).where(merged["成交额_对照"].gt(0) & merged["成交额_当前"].ge(0))
    columns = ["代码", "名称", "价格_当前", "价格_对照", "价格变化", "涨跌幅_当前", "涨跌幅_对照", "涨跌幅变化", "成交额_当前", "成交额_对照", "成交额倍数"]
    return {"current_date": current_date, "baseline_date": baseline_date,
            "added": len(current_codes - previous_codes), "removed": len(previous_codes - current_codes),
            "current_count": len(current), "baseline_count": len(previous), "stocks": merged[columns]}
