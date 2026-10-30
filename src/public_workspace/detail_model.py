"""Original pure detail presentation helpers; no owner data loading."""
import pandas as pd
from .market_groups import market_group_display_mask


def market_group_coverage(df: pd.DataFrame, field: str) -> dict[str, int | float]:
    """Summarize whether the imported market snapshot can support a group map."""
    total = int(len(df))
    classified = int(market_group_display_mask(df, field).sum())
    return {
        "total": total,
        "classified": classified,
        "unclassified": max(0, total - classified),
        "coverage": classified / total if total else 0.0,
    }


def valid_peer_group_fields(df: pd.DataFrame, row_index, candidates: list[str]) -> list[str]:
    """Return only classification fields with a meaningful label for one stock."""
    valid_fields: list[str] = []
    for field in candidates:
        if field not in df.columns or row_index not in df.index:
            continue
        if bool(market_group_display_mask(df, field).loc[row_index]):
            valid_fields.append(field)
    return valid_fields


def quote_export(frame, data):
    result = frame.copy()
    if '快照日期' not in result:
        result['快照日期'] = data.get('import_date') or '未提供'
    result['行情来源'] = {'demo': '演示数据', 'imported': '导入快照'}.get(data.get('stock_quote_source'), '来源未识别')
    return result


def _ashare_change_style(frame: pd.DataFrame, fields=("涨跌幅",)):
    """Subtle table emphasis using the A-share red-up / green-down convention."""
    available = [field for field in fields if field in frame.columns]
    if not available:
        return frame

    def paint(value):
        number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(number) or number == 0:
            return "color: #94a3b8"
        return "color: #ef4444; font-weight: 650" if number > 0 else "color: #22c55e; font-weight: 650"

    return frame.style.map(paint, subset=available)


def rank_peer_quotes(peers, sort_field, ascending=False):
    result = peers.loc[:, ~peers.columns.duplicated()].copy()
    for field in ("涨跌幅", "成交额", "换手率", "综合分"):
        if field in result:
            result[field] = pd.to_numeric(result[field], errors="coerce")
    if sort_field in result:
        result = result.sort_values(sort_field, ascending=ascending, na_position="last", kind="stable")
    return result

