from datetime import datetime,timezone
from streamlit.testing.v1 import AppTest
from src.news_snapshot import save_news_run

def page(directory):
    return AppTest.from_string(f"from src.market_sentiment import render_market_sentiment_page\nrender_market_sentiment_page({{'import_date':'2026-10-13','news_directory':{str(directory)!r}}})").run(timeout=10)

def test_no_snapshot_cannot_show_live_old_samples(tmp_path):
    app=page(tmp_path)
    assert not app.exception
    assert any('暂无有效采集' in value.value for value in app.info)
    assert not any(value.label=='热点主题' for value in app.metric)

def test_historical_samples_toggle_does_not_duplicate_widgets(tmp_path):
    app=page(tmp_path)
    app.checkbox(key='show_historical_news_samples').check().run()
    assert not app.exception

def test_updated_snapshot_displayed_and_category_gap_visible(tmp_path):
    now=datetime.now(timezone.utc)
    save_news_run(tmp_path,[dict(category='政策监管',title='验证的新官方政策',url='https://www.pbc.gov.cn/example',source='中国人民银行',published_at=None,captured_at=now.isoformat(),fact_type='官方发布',summary='')],
        [dict(source='中国人民银行',category='政策监管',status='success',checked_at=now.isoformat(),error=''),dict(source='巨潮资讯',category='公司公告',status='failed',checked_at=now.isoformat(),error='入口不可用')],now)
    app=page(tmp_path)
    assert not app.exception
    assert any('验证的新官方政策' in value.value for value in app.markdown)
    assert any('巨潮资讯' in value.value for value in app.warning)
    assert any('发布时间未知' in value.value for value in app.caption)

def test_calendar_schedule_label_separate_from_publication(tmp_path):
    now=datetime.now(timezone.utc)
    save_news_run(tmp_path,[dict(category='宏观日历',title='官方CPI发布计划',url='https://www.stats.gov.cn/sj/fbrc/bnxxfb/',source='国家统计局',published_at=None,scheduled_at=now.isoformat(),captured_at=now.isoformat(),fact_type='官方计划日程',summary='')],[dict(source='国家统计局',category='宏观日历',status='success',checked_at=now.isoformat(),error='')],now)
    app=page(tmp_path)
    app.session_state['market_signal_category']='宏观日历'
    app.run()
    assert not app.exception
    assert any('计划发布时间' in value.value for value in app.caption)

def test_all_registered_sources_success_not_labeled_partial(tmp_path):
    now=datetime.now(timezone.utc)
    save_news_run(tmp_path,[],[dict(source='测试源',category='政策监管',status='success',checked_at=now.isoformat(),error='')],now)
    app=page(tmp_path)
    assert any(value.label=='采集状态' and value.value=='本次来源采集成功' for value in app.metric)
