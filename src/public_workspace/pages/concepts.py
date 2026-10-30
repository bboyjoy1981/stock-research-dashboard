"""Original ranking layout; explicit concept membership is not listing-board data."""
import pandas as pd
import plotly.express as px
import streamlit as st
from ...calculations import market_sector_tiers
from ..components import public_table
from ..contracts import STOCK_FIELDS

SECTOR_FIELDS=('板块','涨跌幅','成交额','领涨股','股票数')


def render(snapshot,capabilities,navigation):
    dataset=snapshot.optional.get('concepts')
    if dataset is None or dataset.frame.empty:
        st.title('概念与板块排行')
        st.warning('尚未发布可核验的概念归属数据；不把上市板块或行业直接当作概念成分。')
        return
    stocks=snapshot.stocks
    membership=dataset.frame.merge(stocks,on='代码',how='inner',validate='many_to_one')
    sectors=membership.groupby('概念',as_index=False).agg(涨跌幅=('涨跌幅','mean'),成交额=('成交额','sum'),股票数=('代码','count')).rename(columns={'概念':'板块'})
    members={name:group.drop(columns='概念') for name,group in membership.groupby('概念')}
    st.caption(f"概念归属日期：{dataset.metadata['date']}｜行情交易日：{snapshot.metadata['date']}｜归属来源：{dataset.metadata['source']}；归属不是历史时点成分库，仅计算当前快照覆盖成员。")
    missing=len(dataset.frame)-len(membership)
    if missing: st.warning(f'有 {missing} 条概念归属未被当前股票快照覆盖，不补造行情、不按零值计入。')
    render_frame(sectors,stocks,capabilities,navigation,navigation.namespace+'_',members)


def render_frame(sectors,stocks,capabilities,navigation,prefix='',membership=None):
    st.title('概念与板块排行')
    df=sectors[[field for field in SECTOR_FIELDS if field in sectors]].copy().reset_index(drop=True)
    if df.empty or not {'板块','涨跌幅'}.issubset(df):
        st.warning('当前没有可用板块数据，请先导入市场数据。')
        return
    def key(name): return prefix+'concept_'+name
    direction=st.radio('排行方向',['强势排行','弱势排行'],horizontal=True,key=key('direction'))
    maximum=min(50,max(20,len(df)))
    top_n=st.slider('展示板块数量',10,maximum,min(20,maximum),5,key=key('limit'))
    metrics=['涨跌幅','成交额'] if '成交额' in df else ['涨跌幅']
    sort_metric=st.selectbox('排行依据',metrics,key=key('metric'))
    if direction not in ('强势排行','弱势排行') or sort_metric not in metrics or type(top_n) is not int or not 10<=top_n<=maximum:
        st.warning('排行筛选无效。')
        return
    shown=df.sort_values(sort_metric,ascending=direction=='弱势排行')
    a,b,c=st.columns(3)
    a.metric('板块数量',len(df))
    changes=pd.to_numeric(df['涨跌幅'],errors='coerce')
    b.metric('上涨板块',int((changes>0).sum()))
    c.metric('下跌板块',int((changes<0).sum()))
    tiers=market_sector_tiers(df,'板块')
    if not tiers.empty:
        st.subheader('板块强弱梯队',icon=':material/stacked_bar_chart:')
        st.caption('按导入快照中的板块涨跌幅归类，帮助收盘后快速区分领涨、跟随、震荡与承压方向；不构成次日走势判断。')
        order=['强势领涨','偏强跟随','震荡观察','弱势承压']
        counts=tiers['强弱梯队'].value_counts().reindex(order,fill_value=0)
        left,right=st.columns([0.8,1.7],vertical_alignment='top')
        with left,st.container(border=True):
            for name in order: st.metric(name,int(counts[name]),border=True)
        with right,st.container(border=True):
            chart=px.bar(tiers.head(16).sort_values('涨跌幅'),x='涨跌幅',y='板块',color='强弱梯队',orientation='h',
                color_discrete_map={'强势领涨':'#ef4444','偏强跟随':'#fb7185','震荡观察':'#64748b','弱势承压':'#22c55e'})
            chart.update_layout(height=300,margin=dict(t=8,l=0,r=0,b=0),legend_title_text='',xaxis_title='涨跌幅（%）',yaxis_title='')
            st.plotly_chart(chart,width='stretch')
    public_table(shown.head(top_n),SECTOR_FIELDS,capabilities,width='stretch',hide_index=True)
    st.subheader('板块强弱图')
    chart_df=shown.head(top_n).copy()
    chart_df['涨跌幅']=pd.to_numeric(chart_df['涨跌幅'],errors='coerce')
    st.plotly_chart(px.bar(chart_df.sort_values('涨跌幅'),x='涨跌幅',y='板块',orientation='h',color='涨跌幅',color_continuous_scale='RdYlGn_r',color_continuous_midpoint=0),width='stretch')
    if capabilities.download: st.download_button('导出板块排行 CSV',shown.to_csv(index=False,encoding='utf-8-sig'),'sector_ranking.csv','text/csv')
    groups=membership if membership is not None else {name:stocks.loc[stocks['板块'].astype(str).eq(name)].copy() for name in shown['板块'].astype(str)} if '板块' in stocks else {}
    names=[name for name in shown['板块'].astype(str) if name in groups]
    if not names: return
    selected=st.selectbox('查看板块成分股',names,key=key('sector'))
    if selected not in groups:
        st.warning('板块选择无效。')
        return
    def open_selected(detail=False):
        current=navigation.state.get(key('sector'))
        if current not in groups: return
        rows=groups[current].sort_values('涨跌幅',ascending=False)
        allowed=set(stocks['代码']) if '代码' in stocks else set()
        if detail:
            if not rows.empty: navigation.open_stock(rows.iloc[0]['代码'],allowed)
        elif navigation.open_page('大盘云图'):
            navigation.state[navigation.namespace+'_concept']=current
            navigation.state[navigation.namespace+'_concept_codes']=tuple(code for code in rows['代码'] if code in allowed)
    members=groups[selected].copy()
    if '涨跌幅' in members:
        members['涨跌幅']=pd.to_numeric(members['涨跌幅'],errors='coerce')
        members=members.sort_values('涨跌幅',ascending=False)
    st.subheader(f'{selected} 成分股表现')
    with st.container(horizontal=True,vertical_alignment='bottom'):
        st.button('在大盘云图定位',icon=':material/account_tree:',key=key('open_terminal'),on_click=open_selected)
        st.button('进入个股详情',icon=':material/description:',key=key('open_detail'),on_click=open_selected,args=(True,),disabled=members.empty)
    public_table(members.head(30),STOCK_FIELDS,capabilities,width='stretch',hide_index=True)
    if capabilities.download:
        public=members[[field for field in STOCK_FIELDS if field in members]]
        st.download_button('导出当前板块成分股 CSV',public.to_csv(index=False,encoding='utf-8-sig'),'sector_members.csv','text/csv')
    changes=pd.to_numeric(members.get('涨跌幅',pd.Series(dtype=float)),errors='coerce').dropna()
    m1,m2,m3=st.columns(3)
    m1.metric('成分股数量',len(members))
    m2.metric('上涨占比',f'{(changes>0).mean()*100:.1f}%' if not changes.empty else '暂无')
    m3.metric('平均涨跌',f'{changes.mean():+.2f}%' if not changes.empty else '暂无')
