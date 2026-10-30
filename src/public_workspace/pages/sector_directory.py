"""Original directory cards, with injected source data and isolated navigation."""
import pandas as pd
import streamlit as st
from ..classification import prepare_stocks,industry_members,theme_members,THEMES,CHECKED_ON,_number


def render(snapshot,capabilities,navigation):
    render_frame(snapshot.stocks,snapshot.metadata['date'],snapshot.metadata['source'],
        navigation,prefix=navigation.namespace+'_')


def render_frame(stocks,snapshot_date,source,navigation,prefix=''):
    state=navigation.state
    def key(name):
        return prefix+'sector_'+name
    def choose(name,options):
        if name not in options:
            return
        state[key('choice')]=name
        state[key('query')]=''
        state.pop(key('layer'),None)
        state.pop(key('page'),None)
    st.title('板块细分',anchor=False)
    st.caption(f"行业 → 细分环节 → 个股｜快照交易日：{snapshot_date or '未提供'}｜非实时行情")
    if source!='imported':
        st.caption(source)
    frame=prepare_stocks(stocks)
    if frame.empty:
        st.info('尚无可浏览的股票快照，请先导入数据。')
        return
    mode=st.segmented_control('分类方式',['全市场行业','科技精细分类'],default='全市场行业',key=key('mode'))
    if mode not in ('全市场行业','科技精细分类'):
        st.warning('分类方式无效。')
        return
    options=['全部行业',*sorted(frame['浏览行业'].unique())] if mode=='全市场行业' else list(THEMES)
    if state.get(key('choice')) not in options:
        choose(options[0],options)
    choice=state[key('choice')]
    st.caption('行业保留导入原始口径；科技为研究主题，可重复归属。光通信不自动等于 CPO，名单匹配不等于业务已核验。')
    if mode=='科技精细分类':
        st.caption(f'产品参考资料核对于 {CHECKED_ON}，不代表历史时点成分；行情仍取所选快照。名单为首批研究样本，非完整官方成分库。')
    with st.expander('选择板块',expanded=True):
        cols=st.columns(4)
        for index,name in enumerate(options):
            members=industry_members(frame,name) if mode=='全市场行业' else theme_members(frame,name)
            with cols[index%4]:
                st.button(f'{name} · {len(members)} 只',key=key(f'group_{index}'),
                    type='primary' if choice==name else 'secondary',on_click=choose,args=(name,options),width='stretch')
    base=industry_members(frame,choice) if mode=='全市场行业' else theme_members(frame,choice)
    layers=['全部',*THEMES[choice]] if mode=='科技精细分类' else ['全部',*sorted(base['细分行业'].dropna().astype(str).unique())] if '细分行业' in base else ['全部']
    if state.get(key('layer')) not in layers:
        state[key('layer')]='全部'
    layer=st.pills('细分 / 产业链环节',layers,key=key('layer')) or '全部'
    if layer not in layers:
        st.warning('细分筛选无效。')
        return
    result=industry_members(frame,choice,layer) if mode=='全市场行业' else theme_members(frame,choice,layer)
    query=st.text_input('搜索本板块个股',key=key('query'),placeholder='股票名称或代码')
    if query.strip():
        result=result.loc[result['代码'].str.contains(query.strip(),regex=False)|result['名称'].fillna('').astype(str).str.contains(query.strip(),regex=False)]
    st.subheader(f'{choice} · {layer} · {len(result)} 只')
    if result.empty:
        st.info('当前搜索没有匹配个股，请清空搜索或更换关键词。' if query.strip() else '当前快照或标签尚未匹配此环节的个股，不代表市场没有相关公司；需要补充可核验名单。')
        return
    pages=max(1,(len(result)+11)//12)
    if state.get(key('page'),1) not in range(1,pages+1):
        state[key('page')]=1
    page=st.selectbox('个股卡片页',list(range(1,pages+1)),key=key('page'),format_func=lambda n:f'{n} / {pages}')
    if type(page) is not int or page not in range(1,pages+1):
        st.warning('页码无效。')
        return
    cols=st.columns(3)
    allowed_codes=set(frame['代码'])
    for index,(_,row) in enumerate(result.iloc[(page-1)*12:page*12].iterrows()):
        with cols[index%3],st.container(border=True):
            parent=str(row['浏览行业'])
            industry=str(row.get('细分行业',parent))
            st.button(f"{row['名称']} · {row['代码']}",key=key(f"stock_{row['代码']}"),
                on_click=navigation.open_stock,args=(row['代码'],allowed_codes,industry,parent),width='stretch')
            st.metric('收盘价',_number(row,'价格'),_number(row,'涨跌幅',True),delta_color='inverse')
            st.caption(industry)
            if '分类依据' in row:
                st.caption(row['分类依据'])
            if row.get('归属来源'):
                for node,url,note in row['归属证据']:
                    st.markdown(f"[产品依据 · {node}]({url}) · 核对 {row['归属核对日期']}")
                    st.caption(note)
    st.caption('分页仅控制卡片展示，全部匹配成员均可浏览；没有涨幅门槛，不隐藏下跌股票。')
