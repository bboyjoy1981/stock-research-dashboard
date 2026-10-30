"""Validated local news snapshots; network requests never belong in page rendering."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile

from .public_workspace.news_items import CATEGORIES

def timestamp(value):
    from .public_workspace.news_items import timestamp as shared
    return shared(value)

def validate_item(item, now):
    from .public_workspace.news_items import validate_item as shared
    return shared(item,now)

def merge_items(previous,incoming,now):
    now = timestamp(now)
    merged = {item['id']:item for item in (validate_item(row,now) for row in previous)}
    count = 0
    for row in incoming:
        value = validate_item(row,now)
        old = merged.get(value['id'])
        if old is None or any(old.get(key)!=value.get(key) for key in ('title','summary','published_at','scheduled_at')):
            count += 1
        merged[value['id']] = value
    kept = [row for row in merged.values() if timestamp(row.get('scheduled_at') or row['published_at'] or row['captured_at']) >= now-timedelta(days=30)]
    return sorted(kept,key=lambda row:row['published_at'] or row['captured_at'],reverse=True),count

def _atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name = tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as handle:
            json.dump(value,handle,ensure_ascii=False); handle.flush(); os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def load_news_state(directory='data/news',now=None):
    now = timestamp(now or datetime.now(timezone.utc)); directory=Path(directory)
    state = dict(items=[],last_success_at=None,last_attempt_at=None,new_count=0,source_results=[],stale=True)
    paths = [directory/'latest.json',*sorted(directory.glob('snapshot-*.json'),reverse=True)]
    for path in paths:
        try:
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved['version']!=1: raise ValueError('version')
            stamp=timestamp(saved['last_success_at'])
            if stamp>now: raise ValueError('future state')
            rows,_=merge_items(saved['items'],[],now)
            state.update(saved,items=rows,stale=now-stamp>=timedelta(hours=12)); break
        except (OSError,ValueError,KeyError,TypeError): continue
    try:
        attempt=json.loads((directory/'status.json').read_text(encoding='utf-8'))
        timestamp(attempt['last_attempt_at'])
        state.update({key:attempt[key] for key in ('last_attempt_at','source_results','new_count')})
    except (OSError,ValueError,KeyError,TypeError): pass
    return state

def latest_changed_ids(directory='data/news'):
    """IDs added or revised by the latest successful capture, versus its predecessor."""
    snapshots = sorted(Path(directory).glob('snapshot-*.json'), reverse=True)
    if len(snapshots) < 2:
        return set()
    try:
        current = json.loads(snapshots[0].read_text(encoding='utf-8'))
        previous = json.loads(snapshots[1].read_text(encoding='utf-8'))
        old = {row['id']: row for row in previous['items']}
        fields = ('title', 'summary', 'published_at', 'scheduled_at')
        return {row['id'] for row in current['items'] if row['id'] not in old or
                any(row.get(key) != old[row['id']].get(key) for key in fields)}
    except (OSError, ValueError, KeyError, TypeError):
        return set()

def save_news_run(directory,items,source_results,now):
    now=timestamp(now); directory=Path(directory)
    previous=load_news_state(directory,now)
    good=any(row['status']=='success' for row in source_results)
    new_count=0
    if good:
        merged,new_count=merge_items(previous['items'],items,now)
        saved=dict(version=1,items=merged,last_success_at=now.isoformat())
        _atomic(directory/f"snapshot-{now.strftime('%Y%m%dT%H%M%S%f')}.json",saved)
        _atomic(directory/'latest.json',saved)
    _atomic(directory/'status.json',dict(last_attempt_at=now.isoformat(),new_count=new_count,source_results=source_results))
    return load_news_state(directory,now)
