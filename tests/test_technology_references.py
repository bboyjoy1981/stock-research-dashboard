import pandas as pd
from streamlit.testing.v1 import AppTest


def test_reference_matches_without_concept_tags_and_does_not_promote_cpo():
    from src.sector_directory import prepare_stocks, theme_members
    frame = prepare_stocks(pd.DataFrame({'代码': ['300308', '688525', '603986', '688008'], '名称': ['中际旭创', '佰维存储', '兆易创新', '澜起科技'], '行业': ['通信设备', '半导体', '半导体', '半导体']}))
    optics = theme_members(frame, 'CPO / 光通信', '光模块')
    assert optics['代码'].tolist() == ['300308']
    assert optics.iloc[0]['归属来源'].startswith('https://')
    assert theme_members(frame, 'CPO / 光通信', 'CPO').empty
    assert theme_members(frame, '存储', '存储模组')['代码'].tolist() == ['688525']
    assert theme_members(frame, '存储', 'NOR Flash')['代码'].tolist() == ['603986']
    assert theme_members(frame, '存储', '内存接口 / 配套芯片')['代码'].tolist() == ['688008']
    assert theme_members(frame, '存储', 'DRAM')['代码'].tolist() == ['603986']


def test_reference_union_deduplicates_and_preserves_quotes():
    from src.sector_directory import prepare_stocks, theme_members
    frame = prepare_stocks(pd.DataFrame({'代码': ['300308'], '名称': ['中际旭创'], '标签': ['光模块'], '价格': [19.5]}))
    result = theme_members(frame, 'CPO / 光通信')
    assert len(result) == 1
    assert result.iloc[0]['价格'] == 19.5
    assert result.iloc[0]['归属核对日期'] == '2026-10-10'


def test_reference_card_has_evidence_not_a_historical_claim():
    def script():
        import pandas as pd
        import streamlit as st
        from src.sector_directory import render_sector_directory
        st.session_state['sector_mode'] = '科技精细分类'
        render_sector_directory({'stocks': pd.DataFrame({'代码': ['300308'], '名称': ['中际旭创'], '行业': ['通信设备']}), 'import_date': '2026-09-30'})
    at = AppTest.from_function(script).run(timeout=15)
    assert not at.exception
    assert any('产品依据' in x.value and 'https://' in x.value for x in at.markdown)
    assert any('不代表历史时点' in x.value for x in at.caption)


def test_all_product_claims_keep_their_own_links():
    from src.sector_directory import prepare_stocks, theme_members
    frame = prepare_stocks(pd.DataFrame({'代码': ['603986'], '名称': ['兆易创新']}))
    result = theme_members(frame, '存储')
    sources = result.iloc[0]['归属证据']
    assert len(sources) == 2
    assert sources[0][0] == 'NOR Flash'
    assert sources[1][0] == 'DRAM'
    assert sources[0][1] != sources[1][1]
