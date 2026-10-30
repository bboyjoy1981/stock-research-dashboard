"""Original reference panorama and keyword-chain research; no source loading."""
import pandas as pd
import plotly.express as px
import streamlit as st
from ..reference_model import GROUPS,reference_quotes,filter_reference_quotes,reference_summary,reference_export,_change_style
from ...calculations import industry_chain_summary
from ..components import public_table
from ..contracts import STOCK_FIELDS


def render(snapshot,capabilities,navigation):
    render_frame(snapshot.stocks,snapshot.metadata['date'],capabilities,navigation,navigation.namespace+'_')


def render_frame(stocks,snapshot_date,capabilities,navigation,prefix=''):
    view=st.segmented_control('产业链视图',['PCB 参考全景','综合链条'],default='PCB 参考全景',key=prefix+'chain_panorama_view')
    if view=='综合链条':
        render_combined(stocks,capabilities)
    elif view=='PCB 参考全景':
        render_reference_frame(stocks,snapshot_date,capabilities,navigation,prefix)
    else:
        st.warning('产业链视图无效。')


def render_reference_frame(stocks,snapshot_date,capabilities,navigation,prefix=''):
    def key(name): return prefix+'pcb_reference_'+name
    def reset():
        navigation.state.update({key('query'):'',key('layer'):'全部分层',key('sort'):'参考顺序',key('matched'):False})
    st.subheader('A 股 PCB 概念 · 产业链分层全景',icon=':material/account_tree:')
    st.caption(f"名单来源：用户提供的参考图，非实时概念成分库｜行情交易日：{snapshot_date or '未提供'}。分层是研究整理，不代表已核实的当前业务或推荐。")
    quotes=reference_quotes(stocks)
    search,layer,order,coverage=st.columns([2,1.3,1,1])
    query=search.text_input('搜索名称、代码或分层',key=key('query'))
    layers=['全部分层',*[title for title,_,_ in GROUPS]]
    selected_layer=layer.selectbox('产业链分层',layers,key=key('layer'))
    sorts=['参考顺序','涨幅降序','涨幅升序','成交额降序']
    sort=order.selectbox('层内行情排序',sorts,key=key('sort'))
    matched_only=coverage.toggle('仅看快照覆盖',key=key('matched'))
    coverage.button('重置筛选',key=key('reset'),on_click=reset,icon=':material/restart_alt:')
    if selected_layer not in layers or sort not in sorts or type(matched_only) is not bool:
        st.warning('参考名单筛选无效。')
        return
    total=len(quotes)
    quotes=filter_reference_quotes(quotes,query,matched_only,sort)
    if selected_layer!='全部分层': quotes=quotes.loc[quotes['分层'].eq(selected_layer)]
    matched=quotes['行情状态'].eq('已匹配快照').sum()
    st.caption(f'当前显示 {len(quotes)} / {total} 只 · 快照匹配 {matched} 只 · 红涨绿跌；排序与导出均对应当前筛选。')
    if quotes.empty: st.info('没有符合条件的参考股，请清空搜索或关闭仅看快照覆盖。')
    summary=reference_summary(quotes)
    metrics=st.columns(4)
    metrics[0].metric('当前参考名单',f"{summary['rows']} 只")
    metrics[1].metric('快照匹配',f"{summary['matched']} / {summary['rows']}")
    metrics[2].metric('涨跌未知',f"{summary['unknown']} 只")
    metrics[3].metric('有效样本平均涨跌',f"{summary['average']:+.2f}%" if summary['average'] is not None else '—')
    st.caption('平均涨跌为当前有效样本的等权均值，不是 PCB 板块指数。分时与日线评分暂无数据，不显示模拟曲线。')
    visible_codes=set(quotes['代码'])
    allowed_codes=set(quotes.loc[quotes['行情状态'].eq('已匹配快照'),'代码'])
    for number,(title,description,entries) in enumerate(GROUPS,1):
        group=quotes.loc[quotes['分层'].eq(title)]
        entries=[(name,code) for name,code in entries if code in visible_codes]
        if not entries: continue
        left,right=st.columns([1,1.15],vertical_alignment='top')
        with left,st.container(border=True):
            st.markdown(f'**{number}. {title}**')
            st.caption(description)
            for start in range(0,len(entries),4):
                columns=st.columns(4,gap='small')
                for column,(name,code) in zip(columns,entries[start:start+4]):
                    column.button(name,key=prefix+f'pcb_member_{code}',width='stretch',help=f'{name} · {code}',
                        on_click=navigation.open_stock,args=(code,allowed_codes),disabled=code not in allowed_codes)
        with right,st.container(border=True):
            st.markdown(f'**{number}. {title} · 行情**')
            changes=group['涨跌幅'].dropna()
            average=f'{changes.mean():+.2f}%' if len(changes) else '—'
            st.caption(f'名单 {len(group)} 只 · 有效涨跌 {len(changes)} 只 · 平均涨跌 {average} · 上涨 {(changes>0).sum()} / 下跌 {(changes<0).sum()} / 平盘 {(changes==0).sum()}')
            display=group.drop(columns=['分层','综合分']).reset_index(drop=True)
            if capabilities.download:
                st.dataframe(display.style.map(_change_style,subset=['涨跌幅']),hide_index=True,width='stretch',
                    height=min(450,36*(len(group)+1)),column_config={
                        '价格':st.column_config.NumberColumn(format='%.2f'),
                        '涨跌幅':st.column_config.NumberColumn(format='%+.2f%%'),
                        '成交额':st.column_config.NumberColumn(format='compact'),
                        '换手率':st.column_config.NumberColumn(format='%.2f%%')})
            else:
                public_table(display,tuple(display.columns),capabilities,hide_index=True,width='stretch')
    if capabilities.download:
        export=reference_export(quotes,snapshot_date,query,selected_layer,sort,matched_only)
        st.download_button('导出当前 PCB 参考快照',export.to_csv(index=False).encode('utf-8-sig'),
            'pcb_reference_snapshot.csv','text/csv',key=key('export'))


def render_combined(stocks,capabilities):
    st.title('产业链分层')
    df=stocks.loc[:,~stocks.columns.duplicated()].copy()
    fields=[field for field in ('细分行业','行业','标签') if field in df]
    if not fields:
        st.info('当前导入快照没有行业分类字段')
        return
    groups={'半导体 / 存储':('半导体','存储','芯片','集成电路'),
        '算力 / 光通信 / PCB':('算力','光通信','通信','CPO','PCB','服务器'),
        '机器人 / 自动化':('机器人','自动化','工业控制'),
        '有色 / 能源金属':('有色','能源金属','锂','铜','金属')}
    overview=industry_chain_summary(df,groups,fields)
    st.subheader('产业链研究总览',icon=':material/account_tree:')
    st.caption('按行业、细分行业和标签关键词匹配形成研究链条。个股可匹配多条链，因此链条样本数不相加为全市场总数。')
    if not overview.empty:
        strongest=overview.dropna(subset=['平均涨跌']).sort_values('平均涨跌',ascending=False)
        with st.container(horizontal=True):
            st.metric('研究链条',len(overview),border=True)
            st.metric('最强链条',strongest.iloc[0]['产业链'] if not strongest.empty else '—',border=True)
            st.metric('最高平均涨跌',f"{strongest.iloc[0]['平均涨跌']:+.2f}%" if not strongest.empty else '—',border=True)
            st.metric('匹配成交额',f"{overview['成交额'].sum()/1e8:.2f} 亿",border=True)
        left,right=st.columns([1.15,1],vertical_alignment='top')
        with left:
            chart=px.bar(overview.dropna(subset=['平均涨跌']).sort_values('平均涨跌'),x='平均涨跌',y='产业链',orientation='h',color='平均涨跌',color_continuous_scale='RdYlGn_r',color_continuous_midpoint=0,hover_data={'股票数':True,'上涨占比':':.0%','成交额':':.3s'})
            chart.update_layout(height=300,margin=dict(t=8,l=0,r=0,b=0),coloraxis_showscale=False,xaxis_title='平均涨跌幅（%）',yaxis_title='')
            st.plotly_chart(chart,width='stretch')
        with right:
            public_table(overview,tuple(overview.columns),capabilities,width='stretch',hide_index=True,height=300,
                column_config={'股票数':st.column_config.NumberColumn('样本数',format='%,d'),
                    '平均涨跌':st.column_config.NumberColumn('平均涨跌',format='%.2f%%'),
                    '上涨占比':st.column_config.NumberColumn('上涨占比',format='percent'),
                    '成交额':st.column_config.NumberColumn('成交额',format='compact')})
    summary=[]
    selected_groups={}
    for title,terms in groups.items():
        mask=pd.Series(False,index=df.index)
        for field in fields:
            for term in terms: mask|=df[field].fillna('').astype(str).str.contains(term,case=False,regex=False)
        selected=df[mask].copy()
        selected_groups[title]=selected
        changes=pd.to_numeric(selected.get('涨跌幅',pd.Series(index=selected.index,dtype=float)),errors='coerce').dropna()
        summary.append({'产业链':title,'股票数':len(selected),'平均涨跌':f'{changes.mean():+.2f}%' if not changes.empty else '无数据','上涨占比':f'{(changes>0).mean():.1%}' if not changes.empty else '无数据'})
    summary=pd.DataFrame(summary)
    public_table(summary,tuple(summary.columns),capabilities,width='stretch',hide_index=True)
    if capabilities.download: st.download_button('导出产业链强弱摘要 CSV',summary.to_csv(index=False,encoding='utf-8-sig'),'industry_chain_summary.csv','text/csv')
    summary_chart=summary.copy()
    summary_chart['平均涨跌数值']=pd.to_numeric(summary_chart['平均涨跌'].str.replace('%','',regex=False),errors='coerce')
    if summary_chart['平均涨跌数值'].notna().any():
        st.subheader('产业链强弱对比')
        st.bar_chart(summary_chart.set_index('产业链')['平均涨跌数值'])
    st.caption('分层匹配来自导入文件的行业、细分行业或标签字段；一只股可能同时匹配多个关键词。')
    for title,selected in selected_groups.items():
        st.subheader(title)
        public_table(selected.head(100),STOCK_FIELDS,capabilities,width='stretch',hide_index=True)
        if capabilities.download:
            public=selected[[field for field in STOCK_FIELDS if field in selected]]
            st.download_button(f'导出{title}成分股 CSV',public.to_csv(index=False,encoding='utf-8-sig'),f"{title.replace(' ','_')}.csv",'text/csv',key=f'export_chain_{title}')
