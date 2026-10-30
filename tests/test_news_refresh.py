from datetime import datetime,timezone
import importlib
import pytest
NOW=datetime(2026,10,13,8,tzinfo=timezone.utc)
def test_source_failure_does_not_discard_other_news(tmp_path,monkeypatch):
    try: m=importlib.import_module('src.news_refresh')
    except ModuleNotFoundError: pytest.fail('collector not implemented')
    def fetch(source,now):
        if source!='media': raise ValueError('source unavailable')
        return [dict(category='新闻快讯',title='可核验财经新闻标题',url='https://www.chinanews.com.cn/cj/2026/10-13/10713749.shtml',source='中国新闻网',published_at=None,captured_at=now.isoformat(),fact_type='媒体报道',summary='')]
    monkeypatch.setattr(m,'fetch_source',fetch)
    state=m.refresh_news(tmp_path,NOW)
    assert len(state['items'])==1 and state['new_count']==1
    assert any(row['status']=='failed' for row in state['source_results'])
    assert m.refresh_news(tmp_path,NOW)['new_count']==0
