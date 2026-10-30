from datetime import datetime, timedelta, timezone
import importlib
import pytest

NOW = datetime(2026, 10, 13, 8, tzinfo=timezone.utc)

def module():
    try:
        return importlib.import_module('src.news_snapshot')
    except ModuleNotFoundError:
        pytest.fail('news snapshot storage is not implemented')

def item(**changes):
    return dict(category='新闻快讯', title='测试新闻', url='https://example.com/article',
                source='测试源', published_at=None, captured_at=NOW.isoformat(),
                fact_type='媒体报道', summary='', **changes)

def test_unknown_publication_is_not_capture_time():
    assert module().validate_item(item(), NOW)['published_at'] is None

@pytest.mark.parametrize('field,value', [('title',''), ('url','javascript:alert(1)'),
    ('captured_at','2026-10-13T08:00:00'), ('published_at','2026-10-14T08:00:00+00:00')])
def test_invalid_news_rejected(field,value):
    value_item=item(); value_item[field]=value
    with pytest.raises(ValueError): module().validate_item(value_item,NOW)

def test_repeated_and_revised_link():
    m=module(); saved,count=m.merge_items([], [item()],NOW)
    assert count==1
    saved,count=m.merge_items(saved,[item()],NOW)
    assert count==0
    revised=item(); revised['title']='修订标题'
    saved,count=m.merge_items(saved,[revised],NOW)
    assert count==1 and len(saved)==1 and saved[0]['title']=='修订标题'

def test_old_news_pruned_but_known_future_calendar_retained():
    old=item(); old['published_at']=(NOW-timedelta(days=31)).isoformat()
    calendar=item(); calendar.update(category='宏观日历',url='https://example.com/calendar',published_at=(NOW+timedelta(days=1)).isoformat())
    saved,count=module().merge_items([], [old,calendar],NOW)
    assert len(saved)==1 and saved[0]['category']=='宏观日历'

def test_failed_run_preserves_last_success_and_data(tmp_path):
    m=module(); results=[dict(source='测试源',category='新闻快讯',status='success',error='',checked_at=NOW.isoformat())]
    m.save_news_run(tmp_path,[item()],results,NOW)
    failure=[dict(results[0],status='failed',error='连接失败')]
    m.save_news_run(tmp_path,[],failure,NOW+timedelta(hours=1))
    state=m.load_news_state(tmp_path,NOW+timedelta(hours=12))
    assert len(state['items'])==1 and state['last_success_at']==NOW.isoformat()
    assert state['source_results'][0]['status']=='failed' and state['stale']

def test_corrupt_latest_recovers_previous(tmp_path):
    m=module(); results=[dict(source='测试源',category='新闻快讯',status='success',error='',checked_at=NOW.isoformat())]
    m.save_news_run(tmp_path,[item()],results,NOW)
    (tmp_path/'latest.json').write_text('{broken',encoding='utf-8')
    assert len(m.load_news_state(tmp_path,NOW)['items'])==1

def test_wrong_json_type_is_ignored(tmp_path):
    (tmp_path/'latest.json').write_text('[]',encoding='utf-8')
    assert module().load_news_state(tmp_path,NOW)['items']==[]

def test_interrupted_replace_keeps_old_latest(tmp_path,monkeypatch):
    m=module(); results=[dict(source='测试源',category='新闻快讯',status='success',error='',checked_at=NOW.isoformat())]
    m.save_news_run(tmp_path,[item()],results,NOW)
    original=m.os.replace
    def interrupted(source,destination):
        if str(destination).endswith('latest.json'): raise OSError('interrupted')
        return original(source,destination)
    monkeypatch.setattr(m.os,'replace',interrupted)
    revised=item(); revised['title']='更新标题'
    with pytest.raises(OSError): m.save_news_run(tmp_path,[revised],results,NOW)
    assert m.load_news_state(tmp_path,NOW)['items'][0]['title']=='测试新闻'
