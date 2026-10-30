"""Original pure public-news identity, date and link validation."""
from datetime import datetime,timedelta
import hashlib
from urllib.parse import urlsplit,urlunsplit

CATEGORIES=('政策监管','公司公告','宏观日历','新闻快讯')


def timestamp(value):
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('time must include timezone')
    return parsed


def validate_item(item, now):
    now = timestamp(now)
    value = {key: item.get(key) for key in ('category','title','url','source','published_at','captured_at','fact_type','summary')}
    if value['category'] not in CATEGORIES:
        raise ValueError('unknown category')
    for key in ('title','source','fact_type'):
        if not isinstance(value[key],str) or not value[key].strip():
            raise ValueError('missing text')
        value[key] = value[key].strip()[:500]
    url = urlsplit(value['url'])
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:
        raise ValueError('invalid public link')
    value['url'] = urlunsplit((url.scheme,url.netloc,url.path,url.query,''))
    captured = timestamp(value['captured_at'])
    if captured > now:
        raise ValueError('future capture')
    value['captured_at'] = captured.isoformat()
    if value['published_at'] is not None:
        published = timestamp(value['published_at'])
        if published > now and (value['category'] != '宏观日历' or published > now+timedelta(days=30)):
            raise ValueError('future publication')
        value['published_at'] = published.isoformat()
    value['summary'] = (value['summary'] or '')[:300]
    identity=value['url']
    if item.get('scheduled_at') is not None:
        scheduled=timestamp(item['scheduled_at'])
        if value['category']!='宏观日历' or scheduled>now+timedelta(days=30):
            raise ValueError('invalid scheduled event')
        value['scheduled_at']=scheduled.isoformat()
        identity+='|calendar|'+value['title']
    value['id'] = hashlib.sha256(identity.encode()).hexdigest()
    return value

