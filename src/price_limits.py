"""Confirmed close-limit counts require actual per-security limit prices."""
import numpy as np
import pandas as pd


def confirmed_limit_rows(stocks):
    frame = stocks.loc[:, ~stocks.columns.duplicated()].copy()
    if '代码' in frame:
        frame['代码'] = frame['代码'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)
        frame = frame.drop_duplicates('代码', keep='last')
    def values(aliases):
        result = pd.Series(np.nan, index=frame.index)
        for field in aliases:
            if field in frame:
                parsed = pd.to_numeric(frame[field], errors='coerce')
                result = result.fillna(parsed.where(np.isfinite(parsed) & parsed.gt(0)))
        return result
    price = values(['价格', '收盘价', '现价'])
    upper = values(['涨停价', '涨停价格'])
    lower = values(['跌停价', '跌停价格'])
    valid = price.notna() & upper.notna() & lower.notna() & upper.gt(lower)
    valid &= price.le(upper + .000001) & price.ge(lower - .000001)
    frame['限制价格有效'] = valid
    frame['收盘涨停'] = valid & price.sub(upper).abs().lt(.000001)
    frame['收盘跌停'] = valid & price.sub(lower).abs().lt(.000001)
    return frame


def confirmed_limit_counts(stocks):
    frame = confirmed_limit_rows(stocks)
    covered = int(frame['限制价格有效'].sum())
    return {'up': int(frame['收盘涨停'].sum()) if covered else None,
            'down': int(frame['收盘跌停'].sum()) if covered else None,
            'covered': covered, 'total': len(frame)}
