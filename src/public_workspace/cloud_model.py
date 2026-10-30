"""Original pure cloud scope, hierarchy and sector calculations."""
import pandas as pd
from .market_groups import market_group_display_mask


def filter_map_scope(frame, selections):
    result = frame.copy()
    for field, selected in selections.items():
        if selected and selected != '全部' and field in result:
            result = result.loc[result[field].astype(str).eq(str(selected))]
    return result


def market_map_hierarchy_path(df: pd.DataFrame, hierarchy: str) -> list[str]:
    """Keep an available top-level industry above a selected detailed industry."""
    selected = str(hierarchy)
    if (
        selected == "细分行业"
        and df is not None
        and "行业" in df.columns
        and float(market_group_display_mask(df, "行业").mean()) >= 0.15
    ):
        return ["行业", selected]
    return [selected]


def sector_recap(members):
    changes = pd.to_numeric(members.get('涨跌幅', pd.Series(index=members.index, dtype=float)), errors='coerce')
    masks = [changes.lt(-5), changes.ge(-5) & changes.le(-3), changes.gt(-3) & changes.lt(0),
             changes.eq(0), changes.gt(0) & changes.lt(3), changes.ge(3) & changes.lt(5),
             changes.ge(5), changes.isna()]
    distribution = pd.DataFrame({'涨跌区间': ['<-5%', '-5%～-3%', '-3%～0%', '平盘', '0%～3%', '3%～5%', '≥5%', '未知'],
                                 '家数': [int(mask.sum()) for mask in masks],
                                 '颜色': ['#22c55e']*3 + ['#64748b'] + ['#ef4444']*3 + ['#94a3b8']})
    amounts = pd.to_numeric(members.get('成交额', pd.Series(dtype=float)), errors='coerce')
    positive = amounts.loc[amounts.gt(0)].sort_values(ascending=False)
    return {'distribution': distribution,
            'top3_share': float(positive.head(3).sum()/positive.sum()) if len(positive) else None,
            'positive_amount_count': len(positive)}


def sector_snapshot(stocks, field, selected):
    members = stocks.loc[stocks[field].fillna('未分类').astype(str).replace('', '未分类').eq(selected)].copy()
    for name in ('涨跌幅', '成交额', '价格', '换手率'):
        if name in members:
            members[name] = pd.to_numeric(members[name], errors='coerce')
    changes = members.get('涨跌幅', pd.Series(index=members.index, dtype=float)).dropna()
    amounts = members.get('成交额', pd.Series(index=members.index, dtype=float)).dropna()
    return {'members': members, 'rows': len(members), 'valid': len(changes),
            'up': int(changes.gt(0).sum()), 'down': int(changes.lt(0).sum()),
            'flat': int(changes.eq(0).sum()),
            'mean': float(changes.mean()) if len(changes) else None,
            'amount': float(amounts.sum()) if len(amounts) else None,
            'amount_valid': len(amounts)}

