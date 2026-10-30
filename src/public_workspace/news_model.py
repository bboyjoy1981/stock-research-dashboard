"""Audited scalar transport for a structured news snapshot; no source I/O."""
from datetime import timedelta
from zoneinfo import ZoneInfo
import json
import pandas as pd
from .news_items import timestamp,validate_item,CATEGORIES


def validate_public_news_state(value):
    if not isinstance(value,dict):
        raise ValueError('Invalid news state')
    observed=timestamp(value.get('observed_at'))
    result={'observed_at':observed.isoformat()}
    for key in ('last_success_at','last_attempt_at'):
        stamp=value.get(key)
        parsed=timestamp(stamp) if stamp is not None else None
        if parsed is not None and parsed>observed:
            raise ValueError('Future news source state')
        result[key]=parsed.isoformat() if parsed is not None else None
    if result['last_success_at'] and result['last_attempt_at'] and timestamp(result['last_success_at'])>timestamp(result['last_attempt_at']):
        raise ValueError('News success later than latest attempt')
    count=value.get('new_count',0)
    if type(count) is not int or count<0:
        raise ValueError('Invalid news count')
    result['new_count']=count
    items=value.get('items',[])
    sources=value.get('source_results',[])
    if not isinstance(items,list) or not isinstance(sources,list):
        raise ValueError('Invalid news records')
    if items and not result['last_success_at']:
        raise ValueError('News items require successful source provenance')
    result['items']=[validate_item(item,observed) for item in items]
    if result['last_success_at'] and any(timestamp(item['captured_at'])>timestamp(result['last_success_at']) for item in result['items']):
        raise ValueError('News capture later than successful snapshot')
    identities={row['id'] for row in result['items']}
    if len(identities)!=len(items):
        raise ValueError('Duplicate news identity')
    result['source_results']=[]
    seen=set()
    for source in sources:
        if not isinstance(source,dict) or source.get('category') not in CATEGORIES:
            raise ValueError('Invalid news source category')
        if not isinstance(source.get('source'),str) or not source['source'].strip():
            raise ValueError('Missing news source')
        if source.get('status') not in ('success','failed'):
            raise ValueError('Invalid news source status')
        identity=(source['category'],source['source'].strip())
        if identity in seen: raise ValueError('Duplicate news source')
        seen.add(identity)
        checked=timestamp(source.get('checked_at'))
        if checked>observed: raise ValueError('Future news source check')
        row=dict(category=identity[0],source=identity[1],status=source['status'],checked_at=checked.isoformat(),
            error='' if source['status']=='success' else '本次来源不可用；保留最近有效结果，或等待该来源接入。')
        if 'count' in source:
            if type(source['count']) is not int or source['count']<0: raise ValueError('Invalid news source count')
            row['count']=source['count']
        result['source_results'].append(row)
    changed=value.get('changed_ids',[])
    if not isinstance(changed,(list,set,tuple)) or any(not isinstance(i,str) for i in changed):
        raise ValueError('Invalid changed news identities')
    result['changed_ids']=sorted(set(changed)&identities)
    success=timestamp(result['last_success_at']) if result['last_success_at'] else None
    result['stale']=success is None or observed-success>=timedelta(hours=12)
    return result


def news_dataset(state,changed_ids,as_of):
    from .contracts import PublicDataset
    if not isinstance(state,dict): raise ValueError('Invalid news state')
    value=validate_public_news_state(dict(state,observed_at=timestamp(as_of).isoformat(),changed_ids=list(changed_ids)))
    observed=timestamp(value['observed_at'])
    frame=pd.DataFrame([dict(state_json=json.dumps(value,ensure_ascii=False))])
    return PublicDataset('news',frame,dict(date=observed.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat(),
        source='已校验公开资讯快照'))


def decode_news_dataset(dataset,as_of=None):
    if dataset.kind!='news' or len(dataset.frame)!=1 or 'state_json' not in dataset.frame:
        raise ValueError('Invalid typed news source')
    value=validate_public_news_state(json.loads(dataset.frame.iloc[0]['state_json']))
    if as_of is not None:
        now=timestamp(as_of)
        if timestamp(value['observed_at'])>now:
            raise ValueError('Future published news observation')
        last=value['last_success_at']
        value['stale']=last is None or now-timestamp(last)>=timedelta(hours=12)
    return value
