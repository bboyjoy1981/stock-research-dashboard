"""Validate captured two-exchange margin history before descriptive research."""

import numpy as np
import pandas as pd


def parse_margin_history(records, start, end):
    frame = pd.DataFrame(records)
    required = {'DIM_DATE', 'SCDM', 'RZRQYE', 'RZYE', 'RQYE'}
    if not required.issubset(frame.columns):
        raise ValueError('缺少两市余额字段')
    frame['date'] = pd.to_datetime(frame['DIM_DATE'], errors='raise').dt.strftime('%Y-%m-%d')
    frame = frame[frame['date'].between(start, end)].copy()
    if frame.empty or not frame['SCDM'].isin(['007', '001']).all():
        raise ValueError('缺少两市数据或市场代码异常')
    if frame.duplicated(['date', 'SCDM']).any():
        raise ValueError('重复市场日期')
    values = frame[['RZRQYE', 'RZYE', 'RQYE']].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(values).all().all() or (values < 0).any().any():
        raise ValueError('无效余额分量')
    if not np.isclose(values['RZRQYE'], values['RZYE'] + values['RQYE'], rtol=1e-7, atol=1).all():
        raise ValueError('总余额与分量不符')
    if not frame.groupby('date')['SCDM'].nunique().eq(2).all():
        raise ValueError('部分日期缺少两市数据')
    frame['RZRQYE'] = values['RZRQYE']
    return frame.groupby('date')['RZRQYE'].sum().sort_index().astype(float)
