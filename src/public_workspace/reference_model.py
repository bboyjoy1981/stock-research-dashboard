"""Original evidence-labelled PCB reference membership and quote calculations."""
import pandas as pd

GROUPS = [
    ("上游原材料 / 覆铜板 CCL", "覆铜板、铜箔、玻纤与树脂材料；研究分层来自参考图。", [
        ("金安国纪", "002636"), ("南亚新材", "688519"), ("华正新材", "603186"), ("国际复材", "301526"),
        ("宏昌电子", "603002"), ("中国巨石", "600176"), ("生益科技", "600183"), ("宏和科技", "603256"),
        ("铜冠铜箔", "301217"), ("东材科技", "601208"), ("德福科技", "301511"), ("菲利华", "300395")]),
    ("PCB 制造", "高多层板、封装基板与数据中心 PCB 制造。", [
        ("景旺电子", "603228"), ("深南电路", "002916"), ("鹏鼎控股", "002938"), ("广合科技", "001389"),
        ("东山精密", "002384"), ("沪电股份", "002463"), ("生益电子", "688183"), ("胜宏科技", "300476"),
        ("兴森科技", "002436")]),
    ("特色细分 / 二线制造", "软板、汽车板与封装基板等细分研究方向。", [
        ("崇达技术", "002815"), ("超声电子", "000823"), ("依顿电子", "603328"), ("四会富仕", "300852"),
        ("世运电路", "603920"), ("科翔股份", "300903"), ("奥士康", "002913"), ("红板科技", "603459"),
        ("方正科技", "600601"), ("超颖电子", "603175"), ("中富电路", "300814")]),
    ("设备 / 检测 / 设计服务", "PCB 专用设备、检测、激光与打样服务；仅录入参考图可辨识名单。", [
        ("嘉立创", "001232"), ("金百泽", "301041"), ("一博科技", "301366"), ("鼎泰高科", "301377"),
        ("大族数控", "301200")]),
]


def reference_quotes(stocks):
    members = pd.DataFrame([{"分层": title, "名称": name, "代码": code}
                            for title, _, entries in GROUPS for name, code in entries])
    source = stocks.loc[:, ~stocks.columns.duplicated()].copy()
    fields = ["价格", "涨跌幅", "成交额", "换手率", "综合分"]
    if "代码" not in source:
        source = pd.DataFrame(columns=["代码"])
    source["代码"] = source["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    for field in fields:
        source[field] = pd.to_numeric(source[field], errors="coerce") if field in source else float("nan")
    source = source.drop_duplicates("代码", keep="last")
    result = members.merge(source[["代码", *fields]], on="代码", how="left", indicator=True)
    result["行情状态"] = result["_merge"].map({"both": "已匹配快照", "left_only": "快照未覆盖", "right_only": ""}).astype(str)
    return result.drop(columns="_merge")


def filter_reference_quotes(quotes, query="", matched_only=False, sort="参考顺序"):
    result = quotes.copy()
    query = query.strip()
    if query:
        mask = pd.Series(False, index=result.index)
        for field in ("代码", "名称", "分层"):
            mask |= result[field].astype(str).str.contains(query, regex=False, case=False, na=False)
        result = result.loc[mask]
    if matched_only:
        result = result.loc[result["行情状态"].eq("已匹配快照")]
    orders = {"涨幅降序": ("涨跌幅", False), "涨幅升序": ("涨跌幅", True), "成交额降序": ("成交额", False)}
    if sort in orders:
        field, ascending = orders[sort]
        result = result.sort_values(field, ascending=ascending, kind="stable", na_position="last")
    return result


def _change_style(value):
    if pd.isna(value):
        return "color: #94a3b8"
    return "color: #f05261" if value > 0 else "color: #35c99a" if value < 0 else "color: #94a3b8"


def reference_summary(quotes):
    changes = pd.to_numeric(quotes["涨跌幅"], errors="coerce").dropna()
    return {"rows": len(quotes), "matched": int(quotes["行情状态"].eq("已匹配快照").sum()),
            "valid": len(changes), "unknown": len(quotes) - len(changes),
            "average": float(changes.mean()) if len(changes) else None}


def reference_export(quotes, snapshot_date, query, layer, sort, matched_only):
    return quotes.assign(快照日期=snapshot_date or "未提供", 筛选关键词=query,
                         筛选分层=layer, 排序方式=sort, 仅快照覆盖=matched_only)
