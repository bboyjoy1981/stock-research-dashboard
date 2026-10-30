import pandas as pd
from streamlit.testing.v1 import AppTest


def test_allocation_uses_chart_not_duplicate_table():
    app = AppTest.from_string('from src.pages_personal import render_decision_summary\nrender_decision_summary({"score":3})').run()
    assert not app.exception
    assert app.get('plotly_chart')
    assert not app.dataframe


def test_stage_cards_preserve_manual_rule_values():
    from src.personal_visual import stage_cards
    rows = stage_cards(3)
    assert len(rows) == 4
    assert [r['name'] for r in rows if r['active']] == ['修复阶段']
    assert rows[2]['range'] == '60%–70%'


def test_market_context_does_not_change_manual_score():
    from src.personal_visual import render_market_context
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from src.personal_visual import render_market_context
state={'score':3, 'data':{'stocks':pd.DataFrame({'涨跌幅':[1,-1,0]}), 'import_date':'2026-09-30'}}
render_market_context(state)
st.metric('人工评分',state['score'])
''').run()
    assert not app.exception
    assert app.metric[0].value == '3'
    assert any('2026-09-30' in c.value for c in app.caption)


def test_manual_stage_page_has_four_cards_without_rule_table():
    app = AppTest.from_string('''
import src.pages_personal as p
original=p.list_market_snapshots
p.list_market_snapshots=lambda _: []
try:
    p.render_market_score({'score':3,'scores':{},'data':{}})
finally:
    p.list_market_snapshots=original
''').run()
    assert not app.exception
    assert not app.dataframe
    assert sum(m.label == '总仓参考' for m in app.metric) == 4


def test_portfolio_cards_keep_edit_keys_and_hide_duplicate_table():
    app = AppTest.from_string('''
import src.pages_personal as p
original=p.list_portfolio_snapshots
p.list_portfolio_snapshots=lambda _: []
try:
    p.render_portfolio({'score':3})
finally:
    p.list_portfolio_snapshots=original
''').run()
    assert not app.exception
    assert len(app.text_input) == 12
    assert app.number_input(key='holding_amount_0').value == 0
    assert not app.dataframe
    assert not any('编辑' in e.label for e in app.expander)
    assert len(app.get('popover')) == 6
    assert app.get('plotly_chart')
    app.number_input(key='holding_amount_0').set_value(100000).run()
    assert not app.exception
    assert any('100,000' in m.value for m in app.metric)


def test_slot_range_chart_displays_six_ranges_and_pending_slots():
    from src.personal_visual import slot_range_figure
    rows = [{'槽位':f'仓位{i}', '股票':'—', '当前市值':0, '实际占比':0,
             '目标区间':'15%–25%', '仓位状态':'低配'} for i in range(6)]
    figure = slot_range_figure(rows, 1000000)
    assert len(figure.layout.shapes) == 6
    assert len(figure.data[0].x) == 6
    assert all('待配置' in text for text in figure.data[0].text)
    rows[0].update({'股票':'测试股', '当前市值':400000, '实际占比':.4})
    figure = slot_range_figure(rows, 1000000)
    assert figure.data[0].x[0] == .4
    assert figure.layout.xaxis.range[1] > .4
    assert '40.0%' in figure.data[0].text[0]
