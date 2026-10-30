"""Fail-closed public data boundary. No storage, credentials or network access."""
from dataclasses import dataclass, field
from datetime import date
from math import isfinite
import json
from types import MappingProxyType
import pandas as pd

STOCK_FIELDS=('代码','名称','板块','价格','涨跌幅','成交额','行业','细分行业','流通市值','总市值',
    '成交量','成交量单位','成交额单位','换手率','量比','昨收','今开','最高','最低')
INDEX_FIELDS=('名称','价格','点位','涨跌幅','代码','交易日期','来源','源时间','涨跌','昨收','今开','最高','最低')
METADATA_FIELDS=frozenset(('date','source','coverage_key','schema_version'))
OPTIONAL_FIELDS=frozenset(('history','close_limits','news','capital_replay','concepts',
    'industry_chain','index_history','intraday','temperature','daily_history'))


@dataclass(frozen=True)
class PublicCapabilities:
    import_data: bool=False
    download: bool=False
    personal_links: bool=False
    notify: bool=False

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.import_data,self.download,self.personal_links,self.notify)):
            raise ValueError('Capabilities must be explicit booleans')


@dataclass(frozen=True)
class PublicSnapshot:
    stocks: pd.DataFrame
    indices: pd.DataFrame
    metadata: dict
    optional: dict=field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.metadata,dict) or set(self.metadata)-METADATA_FIELDS:
            raise ValueError('Non-public metadata')
        metadata=dict(self.metadata)
        try:
            metadata['date']=date.fromisoformat(metadata['date']).isoformat()
        except (ValueError,KeyError,TypeError):
            raise ValueError('Public snapshot requires an explicit valid date') from None
        if not isinstance(metadata.get('source'),str) or not metadata['source'].strip():
            raise ValueError('Public source required')
        if any(not isinstance(v,(str,int)) or isinstance(v,bool) for v in metadata.values()):
            raise ValueError('Metadata must contain public scalar values')
        if not isinstance(self.optional,dict) or set(self.optional)-OPTIONAL_FIELDS:
            raise ValueError('Non-public optional source')
        if any(value is not None and (not isinstance(value,PublicDataset) or value.kind!=key)
               for key,value in self.optional.items()):
            raise ValueError('Optional payload requires an audited source adapter')
        for name,fields in (('stocks',STOCK_FIELDS),('indices',INDEX_FIELDS)):
            frame=getattr(self,name)
            if not isinstance(frame,pd.DataFrame) or frame.columns.duplicated().any():
                raise ValueError('Invalid public table')
            public=frame[[f for f in fields if f in frame]].copy(deep=True).reset_index(drop=True)
            if any(not pd.api.types.is_scalar(value) for value in public.to_numpy().flat):
                raise ValueError('Public table must contain scalar cells')
            object.__setattr__(self,name,public)
        object.__setattr__(self,'metadata',MappingProxyType(metadata))
        object.__setattr__(self,'optional',MappingProxyType(dict(self.optional)))


@dataclass(frozen=True)
class PublicDataset:
    kind: str
    frame: pd.DataFrame
    metadata: dict

    def __post_init__(self):
        if self.kind not in ('history','index_history','concepts','capital_replay','news','daily_history','temperature','close_limits'):
            raise ValueError('Optional source schema not yet supported')
        base=PublicSnapshot(pd.DataFrame(),pd.DataFrame(),dict(self.metadata))
        fields={'history':(*STOCK_FIELDS,'快照日期'),'index_history':(*INDEX_FIELDS,'快照日期'),
            'concepts':('代码','概念'),
            'capital_replay':('时间','行业','净流入额','涨跌幅','成交额','领涨股','样本数','数据来源','主力净流入占比'),
            'news':('state_json',),
            'close_limits':('state_json',),
            'temperature':('collection','indicator_id','unit','market_coverage','data_period','source_url','version','value','revision','published_at','fetched_at','completed_at','valid_until','publication_basis'),
            'daily_history':('代码','交易日','开盘','最高','最低','收盘','成交量','成交额','换手率','复权方式','成交量单位','成交额单位')}[self.kind]
        if not isinstance(self.frame,pd.DataFrame) or self.frame.columns.duplicated().any():
            raise ValueError('Invalid optional table')
        frame=self.frame[[f for f in fields if f in self.frame]].copy(deep=True).reset_index(drop=True)
        if any(not pd.api.types.is_scalar(v) for v in frame.to_numpy().flat):
            raise ValueError('Invalid optional scalar')
        if self.kind in ('history','index_history'):
            day_field='交易日期' if self.kind=='index_history' and '交易日期' in frame else '快照日期'
            identity='代码' if '代码' in frame else '名称' if self.kind=='index_history' else None
            if day_field not in frame or identity is None or identity not in frame:
                raise ValueError('History requires source dates and identity')
            try: days=frame[day_field].map(lambda v:date.fromisoformat(v).isoformat())
            except (ValueError,TypeError): raise ValueError('Invalid history date') from None
            if not days.empty and days.max()!=base.metadata['date']:
                raise ValueError('History metadata date mismatch')
            if '快照日期' in frame and not frame['快照日期'].eq(days).all():
                raise ValueError('Conflicting history dates')
            if not frame[identity].map(lambda v:isinstance(v,str) and bool(v.strip())).all():
                raise ValueError('Invalid history identity')
            if self.kind=='history' and not frame[identity].str.fullmatch(r'[0-9]{6}').all():
                raise ValueError('Invalid history stock code')
            if frame.assign(_source_day=days).duplicated([identity,'_source_day']).any():
                raise ValueError('Duplicate history observation')
            for column in ('价格','涨跌幅','成交额','成交量'):
                if column not in frame: continue
                values=pd.to_numeric(frame[column],errors='coerce'); present=frame[column].notna()
                if not values[present].map(lambda v:isfinite(float(v))).all(): raise ValueError('Invalid history value')
                if column!='涨跌幅' and values[present].lt(0).any(): raise ValueError('Negative history value')
                if column=='价格' and values[present].le(0).any(): raise ValueError('Invalid history price')
                frame[column]=values
            frame['快照日期']=days
            frame['快照来源']=base.metadata['source']
        if self.kind=='temperature':
            from .temperature_model import validate_public_temperature
            frame=validate_public_temperature(frame,dict(base.metadata))
        if self.kind=='close_limits':
            from .close_pool_model import validate_public_close_pool
            if len(frame)!=1 or 'state_json' not in frame: raise ValueError('Pool requires a structured source snapshot')
            value=validate_public_close_pool(json.loads(frame.iloc[0]['state_json']))
            if value['date']!=base.metadata['date']: raise ValueError('Pool source date mismatch')
            frame.loc[0,'state_json']=json.dumps(value,ensure_ascii=False,allow_nan=False)
        if self.kind=='daily_history':
            required={'代码','交易日','开盘','最高','最低','收盘','复权方式'}
            if not required.issubset(frame): raise ValueError('Incomplete daily history')
            if not frame['代码'].map(lambda v:isinstance(v,str) and len(v)==6 and v.isascii() and v.isdigit()).all():
                raise ValueError('Invalid daily stock code')
            if not frame['复权方式'].isin(('前复权','不复权')).all(): raise ValueError('Unknown daily adjustment')
            try:
                days=frame['交易日'].map(lambda v:date.fromisoformat(v).isoformat())
            except (TypeError,ValueError):
                raise ValueError('Invalid daily date') from None
            if not days.empty and (days.ne(frame['交易日']).any() or days.max()!=base.metadata['date']):
                raise ValueError('Daily source date mismatch')
            if frame.duplicated(['代码','复权方式','交易日']).any(): raise ValueError('Duplicate daily candle')
            for column in ('开盘','最高','最低','收盘','成交量','成交额','换手率'):
                if column not in frame: frame[column]=float('nan')
                values=pd.to_numeric(frame[column],errors='coerce')
                required_price=column in ('开盘','最高','最低','收盘')
                present=pd.Series(True,index=frame.index) if required_price else frame[column].notna()
                if not values[present].map(lambda v:isfinite(float(v))).all(): raise ValueError('Invalid daily value')
                if values[present].lt(0).any() or required_price and values.le(0).any(): raise ValueError('Negative daily value')
                frame[column]=values
            if (frame[['开盘','收盘']].max(axis=1).gt(frame['最高'])|frame[['开盘','收盘']].min(axis=1).lt(frame['最低'])).any():
                raise ValueError('Daily OHLC range mismatch')
            for column,allowed in (('成交量单位',('股','手','源单位未确认')),('成交额单位',('元','万元','亿元','源单位未确认'))):
                if column not in frame: frame[column]='源单位未确认'
                if not frame[column].isin(allowed).all(): raise ValueError('Unknown daily unit')
            frame=frame.sort_values(['代码','复权方式','交易日']).reset_index(drop=True)
        if self.kind=='news':
            from .news_model import validate_public_news_state
            from .news_items import timestamp
            from zoneinfo import ZoneInfo
            if len(frame)!=1 or 'state_json' not in frame or not isinstance(frame.iloc[0]['state_json'],str):
                raise ValueError('News requires one audited structured state')
            value=validate_public_news_state(json.loads(frame.iloc[0]['state_json']))
            if timestamp(value['observed_at']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()!=base.metadata['date']:
                raise ValueError('News observation date mismatch')
            frame.loc[0,'state_json']=json.dumps(value,ensure_ascii=False)
        if self.kind=='capital_replay':
            required={'时间','行业','净流入额','数据来源'}
            if not required.issubset(frame):
                raise ValueError('Capital replay requires explicit timestamps, sectors and sources')
            for column in ('行业','数据来源'):
                if not frame[column].map(lambda v:isinstance(v,str) and bool(v.strip())).all():
                    raise ValueError('Invalid capital source label')
                frame[column]=frame[column].str.strip()
            parsed=pd.to_datetime(frame['时间'],format='%Y-%m-%d %H:%M',errors='coerce')
            if parsed.isna().any() or not frame['时间'].map(lambda v:isinstance(v,str)).all():
                raise ValueError('Invalid capital timestamp')
            if parsed.dt.strftime('%Y-%m-%d %H:%M').ne(frame['时间']).any():
                raise ValueError('Capital timestamp must be explicit minute precision')
            if not parsed.empty and parsed.dt.date.max().isoformat()!=base.metadata['date']:
                raise ValueError('Capital source date does not match latest replay date')
            if frame.duplicated(['时间','行业','数据来源']).any():
                raise ValueError('Duplicate capital source sample')
            if frame.groupby('时间')['数据来源'].nunique().gt(1).any():
                raise ValueError('Mixed capital providers at one timestamp')
            for column in ('净流入额','成交额','涨跌幅','样本数','主力净流入占比'):
                if column not in frame: continue
                values=pd.to_numeric(frame[column],errors='coerce')
                present=frame[column].notna()
                if column=='净流入额' and not present.all():
                    raise ValueError('Missing capital net flow')
                if not values[present].map(lambda v:isfinite(float(v))).all():
                    raise ValueError('Invalid capital value')
                if column in ('成交额','样本数') and values[present].lt(0).any():
                    raise ValueError('Negative capital amount or sample count')
                frame[column]=values
        if self.kind=='concepts':
            if not {'代码','概念'}.issubset(frame):
                raise ValueError('Concept membership requires explicit codes and names')
            if not frame['代码'].map(lambda value:isinstance(value,str) and len(value)==6 and value.isascii() and value.isdigit()).all():
                raise ValueError('Invalid concept member code')
            if not frame['概念'].map(lambda value:isinstance(value,str) and bool(value.strip())).all():
                raise ValueError('Invalid concept name')
            frame['概念']=frame['概念'].str.strip()
            if frame.duplicated(['代码','概念']).any():
                raise ValueError('Duplicate concept membership')
        object.__setattr__(self,'frame',frame)
        object.__setattr__(self,'metadata',base.metadata)
