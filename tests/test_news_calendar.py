from datetime import datetime,timezone
import pytest
import src.news_sources as sources
from src.news_snapshot import merge_items
NOW=datetime(2026,10,14,1,tzinfo=timezone.utc)

def table():
    header='<tr><td>序号</td><td>内容</td>'+''.join(f'<td>{i}月</td>' for i in range(1,13))+'</tr>'
    dates='<tr><td rowspan="2">5</td><td rowspan="2">居民消费价格指数月度报告</td>'+''.join('<td>14/三</td>' if i==10 else '<td rowspan="2">……</td>' for i in range(1,13))+'</tr>'
    return '<h1>2026年国家统计局主要统计信息发布日程表</h1><table>'+header+dates+'<tr><td>9:30</td></tr></table>'

def parse(html):
    assert hasattr(sources,'parse_calendar'),'official calendar parser missing'
    return sources.parse_calendar(html,NOW)

def test_rowspan_calendar_has_scheduled_time_not_publication():
    rows=parse(table())
    assert len(rows)==1
    assert rows[0]['scheduled_at']=='2026-10-14T09:30:00+08:00'
    assert rows[0]['published_at'] is None

def test_unverified_year_and_time_fail():
    for html in (table().replace('2026年',''),table().replace('9:30','待定')):
        with pytest.raises(ValueError): parse(html)

def test_different_events_same_official_page_survive_merge():
    rows=parse(table())
    second=dict(rows[0],title='2026-10-14 工业生产者价格指数月度报告')
    saved,count=merge_items([],rows+[second],NOW)
    assert len(saved)==2 and count==2

def test_revised_time_updates_event_without_two_conflicting_plans():
    rows=parse(table())
    saved,_=merge_items([],rows,NOW)
    revised=dict(rows[0],scheduled_at='2026-10-14T10:00:00+08:00')
    saved,count=merge_items(saved,[revised],NOW)
    assert len(saved)==1 and count==1
    assert saved[0]['scheduled_at']=='2026-10-14T10:00:00+08:00'
