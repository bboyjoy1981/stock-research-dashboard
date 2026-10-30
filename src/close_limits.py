"""Dated close-sealed provider pools; never presented as full-market counts."""
from datetime import datetime, time, date
from zoneinfo import ZoneInfo
from pathlib import Path
import hashlib
import json
import math
import re
import requests

from .public_workspace.close_pool_model import SCOPE,BEIJING,build_close_snapshot

def save_close_snapshot(directory, snapshot):
    encoded=json.dumps(snapshot,ensure_ascii=False,allow_nan=False)
    target=Path(directory)
    target.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(json.dumps([snapshot['up'],snapshot['down']],sort_keys=True).encode()).hexdigest()[:16]
    path=target/f"close_limits_{snapshot['date']}_{digest}.json"
    if not path.exists():
        with path.open('x',encoding='utf-8') as handle:
            handle.write(encoded)
    return path

def load_close_snapshot(directory, day):
    try:
        date.fromisoformat(day)
    except (TypeError,ValueError):
        return None
    for path in sorted(Path(directory).glob(f'close_limits_{day}_*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            value=json.loads(path.read_text(encoding='utf-8'))
            if value['date'] != day or value['schema'] != 1 or not value['scope']:
                continue
            stamp=datetime.fromisoformat(value['captured_at'])
            def payload(rows):
                return {'rc':0,'data':{'qdate':day.replace('-',''),'tc':len(rows),'pool':[
                    {'c':r['代码'],'n':r['名称'],'p':r['价格']*1000,'zdp':r['涨跌幅']} for r in rows]}}
            build_close_snapshot(payload(value['up']),payload(value['down']),day,stamp)
            return value
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            continue
    return None

def fetch_and_save_close_limits(directory, day):
    now=datetime.now(BEIJING)
    # Check the close boundary before making any network request.
    empty={'rc':0,'data':{'qdate':day.replace('-',''),'tc':0,'pool':[]}}
    build_close_snapshot(empty,empty,day,now)
    payloads=[]
    for endpoint,sort in [('getTopicZTPool','fbt:asc'),('getTopicDTPool','fund:asc')]:
        for attempt in range(2):
            try:
                response=requests.get('https://push2ex.eastmoney.com/'+endpoint,
                    params={'ut':'7eea3edcaed734bea9cbfc24409ed989','dpt':'wz.ztzt','Pageindex':0,'pagesize':10000,'sort':sort,'date':day.replace('-','')},
                    timeout=12)
                response.raise_for_status()
                payloads.append(response.json())
                break
            except (requests.RequestException,ValueError):
                if attempt == 1:
                    raise ValueError('涨跌停数据源请求失败；未保存，不代表零家')
    snapshot=build_close_snapshot(*payloads,day,datetime.now(BEIJING))
    return save_close_snapshot(directory,snapshot)

def render_close_limit_metric(stocks,day,snapshot=None):
    from .closing_report import owner_overview_panels
    return owner_overview_panels(dict(stocks=stocks,import_date=day)).render_close_limit_metric(stocks,day,snapshot)
