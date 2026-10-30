"""Audited public temperature observations; no acquisition or persistence."""
import pandas as pd
from urllib.parse import urlparse
from ..temperature_data import COLUMNS,TIME_FIELDS,validate_observations
INDICATOR_GROUP = {
    **{key: '宏观环境' for key in ('cn_pmi', 'us_pmi', 'cn_cpi_yoy', 'us_cpi_yoy',
        'us_core_cpi_yoy', 'cn_policy_rate', 'us_policy_rate', 'eu_policy_rate', 'jp_policy_rate', 'gold', 'oil')},
    **{key: '海外股市' for key in ('sp500', 'nasdaq', 'nikkei225', 'kospi')},
    **{key: 'A股热度' for key in ('a_breadth', 'a_newhigh_low_60', 'a_limit_balance',
        'a_amount', 'sse', 'szse', 'chinext', 'star50', 'csi300', 'a_margin_balance',
        'a_margin_buy_ratio', 'a_new_accounts')},
}
INDICATOR_NAMES = {
    'cn_pmi': '中国制造业PMI', 'us_pmi': '美国制造业PMI',
    'cn_cpi_yoy': '中国CPI同比', 'us_cpi_yoy': '美国CPI同比', 'us_core_cpi_yoy': '美国核心CPI同比',
    'sp500': '标普500', 'nasdaq': '纳斯达克', 'nikkei225': '日经225', 'kospi': 'KOSPI',
    'gold': '黄金基准', 'oil': '原油基准', 'a_amount': 'A股成交额',
    'cn_policy_rate': '中国政策利率（7天逆回购）', 'us_policy_rate': '美国政策利率',
    'eu_policy_rate': '欧元区政策利率（存款便利）', 'jp_policy_rate': '日本政策利率',
    'a_breadth': 'A股上涨占比', 'a_newhigh_low_60': '60日新高新低差占比',
    'a_limit_balance': '涨停跌停差占比', 'sse': '上证指数', 'szse': '深证成指',
    'chinext': '创业板指', 'star50': '科创50', 'csi300': '沪深300',
    'a_margin_balance': '融资余额', 'a_margin_buy_ratio': '融资买入占成交额比例',
    'a_new_accounts': '月度新增开户数',
}

TEMPERATURE_FIELDS=('collection',*COLUMNS,'publication_basis')
SUPPORTING_AMOUNT_SERIES=frozenset(('research_sh_a_amount','research_sz_a_amount','research_margin_buy_amount'))


def validate_public_temperature(frame,metadata):
    if not set(TEMPERATURE_FIELDS).issubset(frame): raise ValueError('Incomplete temperature publication')
    if not frame['collection'].isin(('replay','latest','comparison')).all():
        raise ValueError('Unknown temperature collection')
    if not frame['indicator_id'].isin(set(INDICATOR_GROUP)|SUPPORTING_AMOUNT_SERIES).all(): raise ValueError('Unknown public indicator')
    if not frame.loc[frame['indicator_id'].isin(SUPPORTING_AMOUNT_SERIES),'unit'].eq('CNY').all():
        raise ValueError('Supporting amount requires explicit CNY units')
    if not frame['publication_basis'].isin(('original_release','captured_dataset')).all():
        raise ValueError('Unknown original-publication basis')
    for url in frame['source_url']:
        if not isinstance(url,str): raise ValueError('Invalid public source')
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Invalid public source')
    records=[]
    for name,part in frame.groupby('collection',sort=False):
        valid=validate_observations(part.drop(columns='collection'))
        valid.insert(0,'collection',name)
        records.append(valid)
    result=pd.concat(records,ignore_index=True) if records else frame.copy()
    if not result.empty:
        latest=result['fetched_at'].max()
        if latest.tz_convert('Asia/Shanghai').date().isoformat()!=metadata['date']:
            raise ValueError('Temperature capture date mismatch')
        if latest>pd.Timestamp.now(tz='UTC'): raise ValueError('Future temperature receipt')
    return result.reset_index(drop=True)


def public_inputs(dataset):
    from .contracts import PublicDataset
    if dataset is None: frame=pd.DataFrame(columns=TEMPERATURE_FIELDS)
    else:
        dataset=PublicDataset('temperature',dataset.frame,dict(dataset.metadata))
        frame=dataset.frame
    result={}
    for collection,key in (('replay','temperature_observations'),('latest','temperature_latest_observations'),('comparison','temperature_comparison_observations')):
        result[key]=frame.loc[frame['collection'].eq(collection)].drop(columns='collection').copy()
    return result

