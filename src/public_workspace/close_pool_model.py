"""Pure original provider-pool validator and public projection."""
from datetime import datetime,time,date
from zoneinfo import ZoneInfo
import math,re,json
import pandas as pd

SCOPE = '东方财富专题口径：不含ST、科创板及未中断连续一字板的新股；北交所覆盖未确认，非全A股总数'
BEIJING = ZoneInfo('Asia/Shanghai')

def build_close_snapshot(up_payload, down_payload, day, now):
    trade_day = date.fromisoformat(day)
    if now.tzinfo is None:
        raise ValueError('采集时间缺时区')
    current = now.astimezone(BEIJING)
    if current.date() != trade_day or current.time() < time(15, 30) or trade_day.weekday() >= 5:
        raise ValueError('仅采集当天15:30后的收盘股池；交易所休市日需由任务校验')
    def parse(payload, side):
        try:
            data = payload['data']
            pool = data['pool']
            if payload['rc'] != 0 or str(data['qdate']) != day.replace('-', '') or not isinstance(pool, list) or data['tc'] != len(pool):
                raise ValueError('股池日期或完整性校验失败')
            rows = []
            for item in pool:
                code, name = item['c'], item['n']
                price, change = float(item['p']) / 1000, float(item['zdp'])
                if not isinstance(code, str) or not re.fullmatch(r'\d{6}',code) or not isinstance(name,str) or not name.strip():
                    raise ValueError('股池代码名称无效')
                if not math.isfinite(price) or price <= 0 or not math.isfinite(change) or (side == 'up' and change <= 0) or (side == 'down' and change >= 0):
                    raise ValueError('股池价格方向无效')
                rows.append({'代码':code,'名称':name,'价格':price,'涨跌幅':change})
            if len({row['代码'] for row in rows}) != len(rows):
                raise ValueError('股池代码重复')
            return rows
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError('涨跌停池不可用或校验失败；不能当作零家') from exc
    up, down = parse(up_payload,'up'), parse(down_payload,'down')
    if {row['代码'] for row in up} & {row['代码'] for row in down}:
        raise ValueError('涨跌停池成员冲突')
    return {'date':day,'up':up,'down':down,'scope':SCOPE,'source':'https://quote.eastmoney.com/ztb/',
            'captured_at':current.isoformat(),'date_source':'响应qdate；收盘后采集当前封板池，不含炸板池',
            'schema':1}

def validate_public_close_pool(value):
    if not isinstance(value,dict) or value.get('schema')!=1 or value.get('scope')!=SCOPE or value.get('source')!='https://quote.eastmoney.com/ztb/':
        raise ValueError('Invalid public pool provenance')
    day=value.get('date')
    if not isinstance(day,str) or date.fromisoformat(day).isoformat()!=day:
        raise ValueError('Invalid public pool date')
    stamp=datetime.fromisoformat(value['captured_at'])
    if stamp.tzinfo is None or stamp>datetime.now(BEIJING):
        raise ValueError('Invalid public capture time')
    def payload(side):
        rows=value[side]
        if not isinstance(rows,list) or len(rows)>10000: raise ValueError('Invalid pool members')
        return {'rc':0,'data':{'qdate':value['date'].replace('-',''),'tc':len(rows),'pool':[
            {'c':row['代码'],'n':row['名称'],'p':float(row['价格'])*1000,'zdp':row['涨跌幅']} for row in rows]}}
    return build_close_snapshot(payload('up'),payload('down'),value['date'],stamp)


def close_pool_dataset(value):
    from .contracts import PublicDataset
    clean=validate_public_close_pool(value)
    return PublicDataset('close_limits',pd.DataFrame([{'state_json':json.dumps(clean,ensure_ascii=False,allow_nan=False)}]),
        dict(date=clean['date'],source=clean['scope']))


def decode_close_pool(dataset):
    if dataset.kind!='close_limits' or len(dataset.frame)!=1: raise ValueError('Invalid typed pool')
    clean=validate_public_close_pool(json.loads(dataset.frame.iloc[0]['state_json']))
    if clean['date']!=dataset.metadata['date']: raise ValueError('Pool source date mismatch')
    return clean
