"""Original index layout with explicit data and no source loading."""
import pandas as pd
import plotly.express as px
import streamlit as st
from ...calculations import index_pulse_snapshot
from ..components import public_table
from ..contracts import INDEX_FIELDS


def render(snapshot,capabilities,navigation):
    render_frame(snapshot.indices,capabilities,navigation)


def render_frame(indices,capabilities,navigation):
    """Compatibility boundary for the owner entry's existing index dictionary."""
    st.title('指数分析')
    if not isinstance(indices,pd.DataFrame) or indices.columns.duplicated().any():
        st.warning('当前没有可用指数数据，请先导入或检查数据源。')
        return
    df=indices[[field for field in INDEX_FIELDS if field in indices]].copy().reset_index(drop=True)
    if df.empty or not {'名称','涨跌幅'}.issubset(df):
        st.warning('当前没有可用指数数据，请先导入或检查数据源。')
        return
    dates=sorted(df['交易日期'].dropna().astype(str).unique()) if '交易日期' in df else []
    sources=sorted(df['来源'].dropna().astype(str).unique()) if '来源' in df else []
    st.caption(f"指数交易日：{'、'.join(dates) or '未提供'}｜指数来源：{'、'.join(sources) or '未提供'}；不以个股日期代替。")
    index_sort=st.selectbox('指数排序',['涨跌幅','点位','名称'] if '点位' in df else ['涨跌幅'],
        key=f'{navigation.namespace}_index_sort')
    if index_sort in df:
        df=df.sort_values(index_sort,ascending=index_sort=='名称')
    index_group=st.selectbox('指数范围',['全部指数','A股主要指数','海外与外部指标'],
        key=f'{navigation.namespace}_index_group')
    domestic=df['名称'].astype(str).str.contains('沪深|中证|创业|科创|上证|深证|富时中国',regex=True,na=False)
    if index_group=='A股主要指数':
        df=df[domestic].copy()
    elif index_group=='海外与外部指标':
        df=df[~domestic].copy()
    pulse=index_pulse_snapshot(df)
    if pulse:
        st.subheader('指数市场脉冲',icon=':material/monitoring:')
        st.caption('基于当前筛选范围内的导入指数快照，描述指数横向强弱与分化程度；不是实时行情或方向预测。')
        with st.container(horizontal=True):
            st.metric('上涨 / 下跌',f"{pulse['上涨数量']} / {pulse['下跌数量']}",border=True)
            st.metric('平均涨跌',f"{pulse['平均涨跌']:+.2f}%",border=True)
            st.metric('强弱离散度',f"{pulse['离散度']:.2f}%",border=True)
            st.metric('最强指数',pulse['最强名称'],border=True)
            st.metric('最弱指数',pulse['最弱名称'],border=True)
    if not df.empty:
        best=df.sort_values('涨跌幅',ascending=False).iloc[0]
        worst=df.sort_values('涨跌幅',ascending=True).iloc[0]
        a,b,c=st.columns(3)
        a.metric('指数数量',len(df))
        b.metric('最强指数',str(best.get('名称','—')),f"{float(best['涨跌幅']):+.2f}%")
        c.metric('最弱指数',str(worst.get('名称','—')),f"{float(worst['涨跌幅']):+.2f}%")
    public_table(df,INDEX_FIELDS,capabilities,width='stretch',hide_index=True)
    if capabilities.download:
        st.download_button('导出指数分析 CSV',df.to_csv(index=False,encoding='utf-8-sig'),
            'index_analysis.csv','text/csv',key=f'{navigation.namespace}_index_export')
    if df.empty:
        st.info('当前筛选范围没有可用指数，不生成趋势或补造行情。')
        return
    fig=px.bar(df,x='名称',y='涨跌幅',color='涨跌幅',color_continuous_scale='RdYlGn')
    fig.update_layout(height=390,margin=dict(t=16,l=0,r=0,b=0),coloraxis_showscale=False,xaxis_title='',yaxis_title='涨跌幅（%）')
    st.plotly_chart(fig,width='stretch')
    if {'名称','点位','涨跌幅'}.issubset(df):
        st.subheader('指数位置与涨跌对照')
        scatter=px.scatter(df,x='点位',y='涨跌幅',text='名称',color='涨跌幅',color_continuous_scale='RdYlGn',color_continuous_midpoint=0)
        scatter.update_traces(textposition='top center',marker_size=14)
        scatter.update_layout(height=430,margin=dict(t=20,l=0,r=0,b=0),xaxis_title='指数点位',yaxis_title='涨跌幅（%）')
        st.plotly_chart(scatter,width='stretch')
    st.subheader('指数强弱分区')
    zones=pd.cut(pd.to_numeric(df['涨跌幅'],errors='coerce'),[-100,-1,0,1,100],labels=['明显走弱','弱势震荡','强势震荡','明显走强'])
    zone_counts=zones.value_counts().reindex(['明显走弱','弱势震荡','强势震荡','明显走强'],fill_value=0)
    st.bar_chart(zone_counts)
