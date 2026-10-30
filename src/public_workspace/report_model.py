"""Pure original market activity and factual closing report."""
import pandas as pd
import numpy as np


def activity_totals(data):
    frame = data.get('stocks', pd.DataFrame())
    result = {}
    for field in ['成交额', '成交量']:
        values = pd.to_numeric(frame.get(field, pd.Series(dtype=float)), errors='coerce')
        valid = values.loc[values.ge(0)]
        result[field] = (float(valid.sum()) if len(valid) else None, len(valid), len(frame))
    return result


def activity_comparison(data, field):
    history=data.get('market_history',pd.DataFrame())
    current=data.get('stocks',pd.DataFrame())
    required={'快照日期','代码',field}
    if not required.issubset(history) or not {'代码',field}.issubset(current):
        return '较上日：缺上日数据',None
    dates=sorted(day for day in history['快照日期'].dropna().astype(str).unique() if day<str(data.get('import_date') or ''))
    if not dates: return '较上日：缺上日数据',None
    day=dates[-1]
    prior=history.loc[history['快照日期'].astype(str).eq(day)].copy()
    if field=='成交量':
        if any('成交量单位' not in frame or frame['成交量单位'].isna().any() for frame in (current,prior)):
            return f'较{day}快照：单位未确认',None
        current_units=set(current.get('成交量单位',pd.Series(dtype=str)).dropna())
        prior_units=set(prior.get('成交量单位',pd.Series(dtype=str)).dropna())
        if len(current_units)!=1 or current_units!=prior_units or not current_units.issubset({'股','手'}):
            return f'较{day}快照：单位未确认',None
    for frame in (current,prior):
        if frame['代码'].duplicated().any(): return f'较{day}快照：代码重复',None
    pair=current[['代码',field]].merge(prior[['代码',field]],on='代码',suffixes=('_current','_previous'))
    a=pd.to_numeric(pair[field+'_current'],errors='coerce'); b=pd.to_numeric(pair[field+'_previous'],errors='coerce')
    valid=np.isfinite(a)&np.isfinite(b)&a.ge(0)&b.ge(0)
    base=float(b[valid].sum())
    if not valid.any() or base<=0: return f'较{day}快照：缺有效基准',None
    delta=(float(a[valid].sum())/base-1)*100
    return f'较{day}快照：{delta:+.1f}%',f'{field}按共同有效股票 {int(valid.sum()):,} 只比较；不将较早快照冒称上一交易日。'


def closing_report(data, sectors, field):
    stocks = data.get('stocks', pd.DataFrame())
    changes = pd.to_numeric(stocks.get('涨跌幅', pd.Series(index=stocks.index, dtype=float)), errors='coerce').dropna()
    amounts = pd.to_numeric(stocks.get('成交额', pd.Series(index=stocks.index, dtype=float)), errors='coerce')
    amounts = amounts.loc[amounts.ge(0)]
    source = {'imported':'导入快照','demo':'演示数据'}.get(data.get('stock_quote_source'), '来源未识别')
    average = f'{changes.mean():+.2f}%' if len(changes) else '—'
    date = data.get('import_date') or '日期未提供'
    lines = [f'# A股收盘复盘 · {date}', '', f'数据来源：{source}；非实时。', '',
             '## 市场事实', '',
             f'- 快照样本 {len(stocks):,} 只，有效涨跌 {len(changes):,} 只。',
             f'- 上涨 {int(changes.gt(0).sum())} / 下跌 {int(changes.lt(0).sum())} / 平盘 {int(changes.eq(0).sum())} / 未知 {len(stocks)-len(changes)}。',
             f'- 个股等权平均涨跌 {average}，不是指数涨跌。',
             f'- 有效成交额 {amounts.sum():,.2f} 元，覆盖 {len(amounts)}/{len(stocks)}；不代表资金净流入。' if len(amounts) else '- 成交额未提供，未生成成交规模判断。',
             '', '## 行业强弱', '']
    if field in sectors and '涨跌幅' in sectors and not sectors.empty:
        ranked = sectors.copy()
        ranked['涨跌幅'] = pd.to_numeric(ranked['涨跌幅'], errors='coerce')
        ranked = ranked.dropna(subset=['涨跌幅']).sort_values('涨跌幅', ascending=False)
        for title, subset in [('相对靠前', ranked.head(5)), ('相对靠后', ranked.tail(5).iloc[::-1])]:
            lines.extend([f'### {title}', ''])
            for _, row in subset.iterrows():
                label = str(row[field]).replace('\n',' ')
                count = f"，有效样本 {int(row['股票数'])} 只" if pd.notna(row.get('股票数')) else ''
                lines.append(f"- {label}：等权平均 {row['涨跌幅']:+.2f}%{count}。")
            lines.append('')
        if ranked.empty:
            lines.append('暂无可比较的行业样本。')
    else:
        lines.append('暂无可比较的行业样本。')
    lines.extend(['', '## 复盘检查问题', '',
                  '- 行业强势是多数成分股同步上涨，还是少数股票拉动？在行业研究台核对涨跌分布。',
                  '- 成交是否集中在少数公司？核对前三成交占比，并比较同行。',
                  '- 下一交易日导入后，比较行业广度与成交规模是否延续；当前快照不用于预测确定性收益。',
                  '', '## 数据边界', '',
                  '- 缺失涨跌不计为平盘；部分成交额只汇总已提供样本。',
                  '- 未提供分钟行情、完整K线、公告和新闻时，不生成对应事实或资金流向结论。',
                  '- 本报告仅用于信息整理和研究复盘，不自动下单，不是投资建议。'])
    return '\n'.join(lines)
