from datetime import datetime,timezone
import pytest
import src.news_sources as sources
NOW=datetime(2026,10,14,3,tzinfo=timezone.utc)

def payload():
    return {'classifiedAnnouncements':[[{'secCode':'002475','secName':'立讯精密','announcementTitle':'H股公告-证券变动月报表','announcementTime':1791936131000,'adjunctUrl':'finalpage/2026-10-14/1225604229.PDF'}]],'totalRecordNum':1}

def parse(value):
    assert hasattr(sources,'parse_announcements'),'public announcement parser missing'
    return sources.parse_announcements(value,'announcements',NOW)

def test_verified_announcement_date_and_pdf_link():
    row=parse(payload())[0]
    assert row['published_at']=='2026-10-14T08:02:11+08:00'
    assert row['url']=='https://static.cninfo.com.cn/finalpage/2026-10-14/1225604229.PDF'
    assert row['title'].startswith('002475 立讯精密')

def test_empty_or_foreign_link_rejected():
    with pytest.raises(ValueError): parse({'classifiedAnnouncements':[]})
    value=payload(); value['classifiedAnnouncements'][0][0]['adjunctUrl']='https://bad.example/file'
    with pytest.raises(ValueError): parse(value)

def test_future_announcement_cannot_be_published_now():
    value=payload(); value['classifiedAnnouncements'][0][0]['announcementTime']=1792108800000
    with pytest.raises(ValueError): parse(value)
