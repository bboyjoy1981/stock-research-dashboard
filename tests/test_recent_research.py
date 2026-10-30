from streamlit.testing.v1 import AppTest


def test_navigation_has_only_one_selected_group():
    app = AppTest.from_string('from src.ui import render_sidebar\nrender_sidebar([])')
    app.session_state['active_nav'] = '个股详情'
    app.session_state['market_nav'] = '市场总览'
    app.run()
    assert not app.exception
    assert app.radio(key='market_nav').value == '个股详情'
    assert app.radio(key='personal_nav').value is None
    assert app.radio(key='more_market_nav').value is None


def test_recent_history_deduplicates_and_limits_without_mutation():
    from src.recent_research import remember_stock
    old = [{'code': f'{i:06d}', 'name': str(i)} for i in range(8)]
    result = remember_stock(old, '000003', '更新名称')
    assert result[0] == {'code': '000003', 'name': '更新名称'}
    assert len(result) == 8
    assert old[3]['name'] == '3'
    assert len(remember_stock(result, '600000', '新股票')) == 8


def test_recent_shortcut_preserves_snapshot_and_opens_stock():
    app = AppTest.from_string('from src.ui import render_market_workspace_toolbar\nrender_market_workspace_toolbar("市场总览")')
    app.session_state['recent_research_stocks'] = [{'code': '688008', 'name': '澜起科技'}]
    app.session_state['market_replay_date'] = '2026-09-16'
    app.run()
    app.button(key='recent_stock_688008').click().run()
    assert not app.exception
    assert app.session_state['stock_detail_query'] == '688008'
    assert app.session_state['active_nav'] == '个股详情'
    assert app.session_state['market_replay_date'] == '2026-09-16'


def test_detail_records_selected_stock_for_cross_page_history():
    from pathlib import Path
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py')
    app.session_state['active_nav'] = '个股详情'
    app.session_state['stock_detail_query'] = '688008'
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state['recent_research_stocks'][0]['code'] == '688008'
    app.button(key='workspace_route_市场总览').click().run(timeout=30)
    assert not app.exception
    assert app.radio(key='market_nav').value == '市场总览'
    assert app.button(key='recent_stock_688008')


def test_recent_lookup_clears_unrelated_industry_path_without_changing_date():
    app = AppTest.from_string('from src.ui import render_market_workspace_toolbar\nrender_market_workspace_toolbar("市场总览")')
    app.session_state['recent_research_stocks'] = [{'code': '688008', 'name': '澜起科技'}]
    app.session_state['research_context'] = {'industry': '银行', 'source': '云图'}
    app.session_state['terminal_industry_query'] = '银行'
    app.session_state['market_replay_date'] = '2026-09-16'
    app.run()
    app.button(key='recent_stock_688008').click().run()
    assert not app.exception
    assert 'research_context' not in app.session_state
    assert app.session_state['terminal_industry_query'] == ''
    assert app.session_state['market_replay_date'] == '2026-09-16'


def test_global_search_does_not_carry_industry_context_into_stock_detail():
    app = AppTest.from_string('from src.ui import render_market_workspace_toolbar\nrender_market_workspace_toolbar("市场总览")')
    app.session_state['research_context'] = {'industry': '银行', 'source': '云图'}
    app.run()
    app.text_input(key='workspace_stock_query').set_value('688008').run()
    assert not app.exception
    assert app.session_state['stock_detail_query'] == '688008'
    assert 'research_context' not in app.session_state


def test_clear_recent_history_preserves_current_research_and_snapshot():
    app = AppTest.from_string('from src.ui import render_market_workspace_toolbar\nrender_market_workspace_toolbar("市场总览")')
    app.session_state['recent_research_stocks'] = [{'code': '688008', 'name': '澜起科技'}]
    app.session_state['research_context'] = {'industry': '半导体', 'source': '云图'}
    app.session_state['market_replay_date'] = '2026-09-16'
    app.run()
    app.button(key='clear_recent_research').click().run()
    assert not app.exception
    assert app.session_state['recent_research_stocks'] == []
    assert app.session_state['research_context']['industry'] == '半导体'
    assert app.session_state['market_replay_date'] == '2026-09-16'
    assert not any(b.key == 'recent_stock_688008' for b in app.button)


def test_detail_does_not_offer_clear_that_would_immediately_rerecord_current_stock():
    app = AppTest.from_string('from src.ui import render_market_workspace_toolbar\nrender_market_workspace_toolbar("个股详情")')
    app.session_state['recent_research_stocks'] = [{'code': '688008', 'name': '澜起科技'}]
    app.run()
    assert not app.exception
    assert not any(b.key == 'clear_recent_research' for b in app.button)
