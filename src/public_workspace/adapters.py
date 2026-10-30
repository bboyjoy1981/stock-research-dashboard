"""Pure adapters: never load files, personal stores, credentials or demo fallback."""
from datetime import date
import numpy as np
import pandas as pd
from .contracts import PublicSnapshot, PublicDataset, METADATA_FIELDS


def _validate_quotes(snapshot):
    stocks=snapshot.stocks
    required={'代码','名称','板块','价格','涨跌幅','成交额'}
    if stocks.empty or not required.issubset(stocks):
        raise ValueError('Public stock quotes unavailable')
    if not stocks['代码'].map(lambda v:isinstance(v,str) and len(v)==6 and v.isascii() and v.isdigit()).all() or stocks['代码'].duplicated().any():
        raise ValueError('Invalid public stock identity')
    if not snapshot.indices.empty and not {'名称','价格','涨跌幅'}.issubset(snapshot.indices):
        raise ValueError('Incomplete public index quotes')
    for frame in (stocks,snapshot.indices):
        if frame.empty: continue
        for name in ('名称','板块'):
            if name in frame and not frame[name].map(lambda v:isinstance(v,str) and bool(v.strip())).all():
                raise ValueError('Missing public quote label')
        for name in ('价格','涨跌幅','成交额'):
            if name not in frame: continue
            values=pd.to_numeric(frame[name],errors='coerce')
            if not np.isfinite(values).all() or name=='价格' and values.le(0).any() or name=='成交额' and values.lt(0).any():
                raise ValueError('Invalid public quote value')
            frame[name]=values
    return snapshot


def _dated_index_history(old,before):
    """History requires the index source's own date, never the stock date."""
    if old.indices.empty or '交易日期' not in old.indices:
        return None
    frame=old.indices.copy()
    try:
        dates=frame['交易日期'].map(lambda value:date.fromisoformat(value).isoformat())
    except (ValueError,TypeError):
        return None
    frame['快照日期']=dates
    frame=frame.loc[dates.lt(before)].copy()
    if frame.empty:
        return None
    metadata=dict(old.metadata,date=frame['快照日期'].max())
    return PublicDataset('index_history',frame,metadata)


def from_published(data):
    if not isinstance(data,dict) or not isinstance(data.get('metadata'),dict):
        raise ValueError('Published snapshot unavailable')
    meta={k:v for k,v in data['metadata'].items() if k in METADATA_FIELDS}
    source=meta.get('source','')
    if not isinstance(source,str) or '演示' in source or 'demo' in source.lower():
        raise ValueError('Published demo fallback forbidden')
    current=_validate_quotes(PublicSnapshot(data.get('stocks'),data.get('indices'),meta,data.get('optional',{})))
    optional=_copy_optionals(current,published=True)
    prior=data.get('previous')
    if isinstance(prior,dict) and isinstance(meta.get('coverage_key'),str) and meta['coverage_key'].strip():
        try:
            old=from_published({k:v for k,v in prior.items() if k!='previous'})
            if old.metadata.get('coverage_key')==meta['coverage_key'] and old.metadata['date']<current.metadata['date']:
                history=old.stocks.copy()
                history['快照日期']=old.metadata['date']
                optional['history']=PublicDataset('history',history,dict(old.metadata))
                index_history=_dated_index_history(old,current.metadata['date'])
                if index_history is not None:
                    optional['index_history']=index_history
        except (ValueError,KeyError,TypeError):
            pass
    return PublicSnapshot(current.stocks,current.indices,dict(current.metadata),optional)


def from_local_research(data):
    if not isinstance(data,dict):
        raise ValueError('Local public research data unavailable')
    origin=data.get('stock_quote_source')
    source={'imported':'本地导入公开研究快照；非实时行情','demo':'演示数据；非真实行情'}.get(origin,'公开来源未确认')
    meta=dict(date=data.get('import_date'),source=source)
    scope=data.get('coverage_key')
    if isinstance(scope,str) and scope.strip(): meta['coverage_key']=scope
    # Only actual independently collected indices are exposed, never owner indices/demo fallback.
    indices=data.get('index_snapshot',pd.DataFrame())
    current=_validate_quotes(PublicSnapshot(data.get('stocks'),indices,meta,data.get('optional',{})))
    prior=data.get('previous')
    optional=_copy_optionals(current)
    if isinstance(prior,dict) and origin=='imported':
        try:
            old=from_local_research({k:v for k,v in prior.items() if k!='previous'})
            scope=meta.get('coverage_key')
            if (prior.get('stock_quote_source')=='imported' and scope
                    and old.metadata.get('coverage_key')==scope
                    and old.metadata['date']<meta['date']):
                history=old.stocks.copy()
                history['快照日期']=old.metadata['date']
                optional['history']=PublicDataset('history',history,dict(old.metadata))
        except (ValueError,KeyError,TypeError):
            pass
    return PublicSnapshot(current.stocks,current.indices,dict(current.metadata),optional)


def _copy_optionals(snapshot,published=False):
    result={}
    for kind,item in snapshot.optional.items():
        if item is None:
            result[kind]=None
            continue
        if kind in ('history','index_history') and item.metadata['date']>=snapshot.metadata['date']:
            continue
        if kind=='history' and published:
            coverage=snapshot.metadata.get('coverage_key')
            if not coverage or coverage!=item.metadata.get('coverage_key'):
                continue
        source=item.metadata['source']
        if published and ('演示' in source or 'demo' in source.lower()):
            raise ValueError('Published optional demo fallback forbidden')
        result[kind]=PublicDataset(kind,item.frame,dict(item.metadata))
    return result
