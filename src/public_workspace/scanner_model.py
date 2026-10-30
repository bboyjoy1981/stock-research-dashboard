"""Original pure candidate filters, quote facts and classification-field selection."""
import pandas as pd


def filter_candidates(frame, query="", group_field=None, group="全部", minimum_change=0.0,
                      minimum_amount=0.0, sort_field="涨跌幅", ascending=False, market="全部市场", minimum_score=None, maximum_risk=None):
    result = frame.loc[:, ~frame.columns.duplicated()].copy()
    prefixes = {"沪市主板": ("60",), "深市主板": ("00",), "创业板": ("30",), "科创板": ("68",), "北交所": ("43", "83", "87", "92")}
    if market != "全部市场":
        if market not in prefixes or "代码" not in result:
            return result.iloc[:0]
        codes = result["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
        result = result.loc[codes.str.startswith(prefixes[market])]
    for field in ("价格", "涨跌幅", "成交额", "换手率", "量比", "综合分", "风险分"):
        if field in result:
            result[field] = pd.to_numeric(result[field], errors="coerce")
    for field, threshold, lower in (("综合分", minimum_score, True), ("风险分", maximum_risk, False)):
        if threshold is not None:
            if field not in result:
                return result.iloc[:0]
            result = result.loc[result[field].ge(threshold) if lower else result[field].le(threshold)]
    if "涨跌幅" in result:
        result = result.loc[result["涨跌幅"].ge(minimum_change)]
    if minimum_amount > 0:
        if "成交额" not in result:
            return result.iloc[:0]
        result = result.loc[result["成交额"].ge(minimum_amount)]
    if group_field in result and group != "全部":
        result = result.loc[result[group_field].fillna("").astype(str).eq(group)]
    query = query.strip()
    if query:
        mask = pd.Series(False, index=result.index)
        for field in ("代码", "名称", "标签"):
            if field in result:
                mask |= result[field].fillna("").astype(str).str.contains(query, case=False, regex=False)
        result = result.loc[mask]
    if sort_field in result:
        result = result.sort_values(sort_field, ascending=ascending, na_position="last")
    return result


def candidate_review_report(*, date, origin, sample_count, matched_count, displayed_count,
                            query, market, group, minimum_change, minimum_amount,
                            sort_field, minimum_score=None, maximum_risk=None):
    """Portable screening context; never turn imported scores into predictions."""
    return "\n".join([
        "候选筛选 · 收盘复盘口径",
        f"快照交易日：{date or '未提供'}", f"数据来源：{origin}",
        f"输入样本：{sample_count:,}", f"符合条件：{matched_count:,}",
        f"卡片展示：{displayed_count:,}", f"市场范围：{market}",
        f"行业 / 产业链：{group}", f"搜索：{query.strip() or '无'}",
        f"最低涨幅：{minimum_change:+.2f}%",
        f"最低成交额：{minimum_amount / 1e8:.2f} 亿元",
        f"综合分门槛：{minimum_score if minimum_score is not None else '未启用'}",
        f"风险分上限：{maximum_risk if maximum_risk is not None else '未启用'}",
        f"排序：{sort_field} · {'由低到高' if sort_field == '风险分' else '由高到低'}",
        "完整清单导出不受卡片展示上限限制。",
        "基于所选快照，不是实时行情；缺失字段不补造，评分仅为导入值。",
        "仅供研究复盘，不代表交易建议或收益预测。",
    ])


def _number(row, field):
    return pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").iloc[0]


def _display(row, field, money=False, percent=False):
    number = _number(row, field)
    if pd.isna(number):
        return "—"
    if field == "价格" and number <= 0:
        return "—"
    if money:
        return f"{number / 1e8:.2f} 亿"
    return f"{number:+.2f}%" if percent else f"{number:.2f}"


def quote_detail_values(row):
    aliases = {"昨收": ["昨收", "昨收价", "前收盘价"], "今开": ["今开", "开盘价", "开盘"],
               "最高": ["最高", "最高价"], "最低": ["最低", "最低价"]}
    values = {}
    for label, fields in aliases.items():
        values[label] = "—"
        for field in fields:
            number = _number(row, field)
            if pd.notna(number) and number > 0:
                values[label] = f"{number:.2f}"
                break
    return values


def select_market_group_column(df: pd.DataFrame, minimum_coverage: float = 0.15) -> str:
    """Choose the most detailed reliable category field in a terminal export."""
    if df is None or df.empty:
        return "\u677f\u5757"
    for field in ("\u7ec6\u5206\u884c\u4e1a", "\u884c\u4e1a"):
        if field not in df.columns:
            continue
        values = df[field].fillna("").astype(str).str.strip()
        coverage = float(values.ne("").mean())
        if coverage >= minimum_coverage:
            return field
    return "\u677f\u5757" if "\u677f\u5757" in df.columns else next(iter(df.columns), "\u677f\u5757")

