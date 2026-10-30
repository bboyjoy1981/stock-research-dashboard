"""Original cloud controls/components/sector panels over supplied public frames."""
import pandas as pd
import streamlit as st
from ..cloud_model import filter_map_scope,sector_recap,sector_snapshot
from ..components import public_table
from ..detail_model import quote_export


def display_table(frame,capabilities,**kwargs):
    if capabilities.download: return st.dataframe(frame,**kwargs)
    if not isinstance(frame,pd.DataFrame): frame=frame.data
    return public_table(frame,tuple(frame.columns),capabilities,**kwargs)


def reset_scope(state,prefix=""):
    state[prefix+'core_cloud_parent']='全部'
    state[prefix+'core_cloud_group']='全部'
    state.pop(prefix+'core_cloud_stock',None)


def focus_sector(stocks,field,value,navigation):
    if field not in stocks or value not in set(stocks[field].dropna().astype(str)): return False
    if field=='细分行业':
        if '行业' not in stocks: return False
        pairs=set(zip(stocks['行业'],stocks[field]))
        parents={p for p,c in pairs if c==value}
        if len(parents)!=1: return False
        parent=next(iter(parents))
    else:
        pairs={(v,v) for v in stocks[field].dropna().astype(str)}
        parent=value
    return navigation.focus_sector(field,value,pairs,parent)


def open_stock_widget(frame,hierarchy,label,navigation,prefix="",source='大盘云图 · 成分股'):
    if not isinstance(label,str) or '个股' not in frame: return False
    selected=frame.loc[frame['个股'].eq(label)]
    if selected.empty: return False
    row=selected.iloc[0]
    code=label.split(' · ',1)[0]
    allowed=set(frame['个股'].astype(str).str.split(' · ',n=1).str[0])
    parent=str(row['行业']) if hierarchy=='细分行业' and '行业' in row and pd.notna(row['行业']) else None
    industry=str(row[hierarchy]) if hierarchy in row and pd.notna(row[hierarchy]) else None
    if not navigation.open_stock(code,allowed,industry,parent): return False
    state=navigation.state
    context=dict(source=source,industry=industry,field=hierarchy,parent=parent)
    state[prefix+'research_context']=context
    state[prefix+'stock_detail_query']=code
    state.pop(prefix+'stock_detail_selection',None)
    return True


def render_exact_cloud_scope(grouped, hierarchy, parent, capabilities, navigation, prefix=""):
    """Parent and child selections are exact, not keyword matches."""
    state=navigation.state
    def reset_cloud_scope():
        reset_scope(state,prefix)
    selections = {}
    controls = st.columns([1, 1, .6] if parent else [2, .6], vertical_alignment='bottom')
    position = 0
    if parent:
        options = ['全部', *sorted(grouped[parent].dropna().astype(str).unique())]
        if state.get(prefix+'core_cloud_parent') not in options:
            state[prefix+'core_cloud_parent'] = '全部'
        with controls[0]:
            selections[parent] = st.selectbox(f'下钻一级 · {parent}', options, key=prefix+'core_cloud_parent', persist_state='session')
        position = 1
    subset = filter_map_scope(grouped, selections)
    options = ['全部', *sorted(subset[hierarchy].dropna().astype(str).unique())]
    if state.get(prefix+'core_cloud_group') not in options:
        state[prefix+'core_cloud_group'] = '全部'
    with controls[position]:
        selections[hierarchy] = st.selectbox(f'下钻分类 · {hierarchy}', options, key=prefix+'core_cloud_group', persist_state='session')
    with controls[-1]:
        st.button('返回上层', icon=':material/undo:', key=prefix+'core_cloud_back', on_click=reset_cloud_scope, width='stretch')
    selected = [str(value) for value in selections.values() if value != '全部']
    st.caption('当前位置：全市场' + (' → ' + ' → '.join(selected) if selected else '') + ' → 个股；可点击地图分类放大，或使用上方精确下钻。')
    return filter_map_scope(grouped, selections)


def render_cloud_components(leaves, hierarchy, size_field, capabilities, navigation, prefix=""):
    def table(frame,**kwargs):
        return display_table(frame,capabilities,**kwargs)
    state=navigation.state
    def open_selected():
        open_stock_widget(leaves,hierarchy,state.get(prefix+'core_cloud_stock'),navigation,prefix)
    with st.expander('当前地图成分股 · 点击研究', expanded=False):
        if leaves.empty:
            st.caption('当前范围没有可用个股。')
            return
        ranked = leaves.sort_values('面积', ascending=False)
        options = ranked['个股'].drop_duplicates().tolist()
        if state.get(prefix+'core_cloud_stock') not in options:
            state[prefix+'core_cloud_stock'] = options[0]
        columns = st.columns([3, 1], vertical_alignment='bottom')
        with columns[0]:
            selected = st.selectbox('当前范围个股', options, key=prefix+'core_cloud_stock')
        with columns[1]:
            row = ranked.loc[ranked['个股'].eq(selected)].iloc[0]
            st.button('研究此股', key=prefix+'core_cloud_open_stock', icon=':material/open_in_new:',
                      on_click=open_selected, width='stretch')
        table(ranked[['个股', hierarchy, '涨跌幅', '面积']].head(30), hide_index=True,
                     column_config={'涨跌幅': st.column_config.NumberColumn('涨跌幅', format='%+.2f%%'),
                                    '面积': st.column_config.NumberColumn(size_field, format='compact')},
                     width='stretch', height=250)
        st.caption(f'当前范围 {len(leaves):,} 只，表格显示规模靠前 30 只；完整明细可由地图导出。')


def render_sector_recap(members):
    import altair as alt
    recap = sector_recap(members)
    left, right = st.columns([1.4, 1])
    with left:
        st.markdown('**行业内部涨跌分布**')
        chart = alt.Chart(recap['distribution']).mark_bar().encode(
            x=alt.X('涨跌区间:N', sort=recap['distribution']['涨跌区间'].tolist(), axis=alt.Axis(labelAngle=0)),
            y=alt.Y('家数:Q', axis=alt.Axis(tickMinStep=1)), color=alt.Color('颜色:N', scale=None),
            tooltip=['涨跌区间:N', '家数:Q']).properties(height=210)
        st.altair_chart(chart, width='stretch')
    with right:
        st.markdown('**成交集中度 · 前三只**')
        share = recap['top3_share']
        if share is None:
            st.caption('没有正成交额数据，未生成集中度。')
        else:
            st.metric('占本分类有效成交额', f'{share:.1%}')
            split = pd.DataFrame({'范围': ['前三只', '其余'], '成交占比': [share, 1-share]})
            chart = alt.Chart(split).mark_bar().encode(
                y=alt.Y('范围:N', sort=['前三只', '其余']), x=alt.X('成交占比:Q', axis=alt.Axis(format='%'), scale=alt.Scale(domain=[0,1])),
                color=alt.Color('范围:N', scale=alt.Scale(range=['#38bdf8','#64748b']), legend=None),
                tooltip=[alt.Tooltip('成交占比:Q', format='.1%')]).properties(height=110)
            st.altair_chart(chart, width='stretch')
        st.caption(f"有效正成交额 {recap['positive_amount_count']} 只；只描述快照成交规模，不代表资金净流向。")


def render_sector_lens(stocks, field, data, prefix, capabilities, navigation,session_prefix=None):
    state=navigation.state
    context_prefix=navigation.namespace+'_' if session_prefix is None else session_prefix
    def table(frame,**kwargs):
        return display_table(frame,capabilities,**kwargs)
    def download(*args,**kwargs):
        if capabilities.download: return st.download_button(*args,**kwargs)
    if field not in stocks or stocks.empty:
        return
    scope = stocks
    if field == '细分行业' and '行业' in stocks:
        parent_options = ['全部', *sorted(stocks['行业'].fillna('未分类').astype(str).replace('', '未分类').unique())]
        parent_key = f'{prefix}_parent'
        if state.get(parent_key) not in parent_options:
            state[parent_key] = '全部'
        parent_scope = st.selectbox('研究上级行业', parent_options, key=parent_key)
        if parent_scope != '全部':
            scope = stocks.loc[stocks['行业'].fillna('未分类').astype(str).replace('', '未分类').eq(parent_scope)]
    options = sorted(scope[field].fillna('未分类').astype(str).replace('', '未分类').unique())
    if not options:
        st.info('当前分类范围没有可用行业。')
        return
    key = f'{prefix}_sector'
    if state.get(key) not in options:
        context = state.get(context_prefix+'research_context', {}).get('industry')
        state[key] = context if context in options else next((v for v in options if v not in {'未分类', '未细分'}), options[0])
    with st.container(border=True):
        st.subheader('行业研究台', icon=':material/hub:')
        controls = st.columns([2, 1], vertical_alignment='bottom')
        with controls[0]:
            selected = st.selectbox(f'研究分类 · {field}', options, key=key)
        summary = sector_snapshot(scope, field, selected)
        members = summary['members']
        parent = None
        if field == '细分行业' and '行业' in members:
            parents = members['行业'].fillna('未分类').astype(str).replace('', '未分类').unique()
            parent = str(parents[0]) if len(parents) == 1 else None
        def open_current_sector():
            selected_now=state.get(key)
            if selected_now not in options: return
            focus_sector(scope,field,selected_now,navigation)
        with controls[1]:
            st.button('定位行业云图', key=f'{prefix}_open_cloud', icon=':material/account_tree:',
                      on_click=open_current_sector, width='stretch')
        with st.container(horizontal=True):
            st.metric('成分股 / 有效涨跌', f"{summary['rows']} / {summary['valid']}", border=True)
            st.metric('行业等权涨跌', f"{summary['mean']:+.2f}%" if summary['mean'] is not None else '—', border=True)
            st.metric('上涨 / 下跌 / 平盘', f"{summary['up']} / {summary['down']} / {summary['flat']}", border=True)
            st.metric('成分股成交额', f"{summary['amount']/1e8:.2f} 亿" if summary['amount'] is not None else '—', border=True)
        st.caption(f"{selected} · {data.get('import_date') or '日期未提供'} · 当前页面范围内成分股；缺失涨跌 {summary['rows']-summary['valid']} 只，成交额覆盖 {summary['amount_valid']}/{summary['rows']}。等权涨跌不是行业指数，成交额不是资金净流入。")
        with st.expander('行业复盘图 · 涨跌分布与成交集中度', expanded=True):
            render_sector_recap(members)
        fields = [name for name in ('代码', '名称', '涨跌幅', '价格', '成交额') if name in members]
        config = {'涨跌幅': st.column_config.NumberColumn(format='%+.2f%%'),
                  '成交额': st.column_config.NumberColumn(format='compact')}
        for column, (title, rank, ascending) in zip(st.columns(3), [('领涨成分股', '涨跌幅', False), ('领跌成分股', '涨跌幅', True), ('成交活跃股', '成交额', False)]):
            with column:
                st.markdown(f'**{title}**')
                ranked = members.dropna(subset=[rank]).sort_values(rank, ascending=ascending) if rank in members else members.iloc[:0]
                if rank == '涨跌幅' and not ranked.empty:
                    ranked = ranked.loc[ranked[rank].lt(0) if ascending else ranked[rank].gt(0)]
                if rank == '成交额' and not ranked.empty:
                    ranked = ranked.loc[ranked[rank].gt(0)]
                if ranked.empty:
                    st.caption('当前分类无下跌样本' if rank == '涨跌幅' and ascending else '当前分类无上涨样本' if rank == '涨跌幅' else '当前分类未提供有效成交额')
                else:
                    table(ranked[fields].head(8), hide_index=True, width='stretch', height=300, column_config=config)
        if '代码' in members and not members.empty:
            labels = (members['代码'].astype(str) + ' · ' + members.get('名称', pd.Series('未命名', index=members.index)).fillna('未命名').astype(str)).drop_duplicates().tolist()
            member_key = f'{prefix}_member'
            if state.get(member_key) not in labels:
                state[member_key] = labels[0]
            actions = st.columns([2, 1, 1], vertical_alignment='bottom')
            with actions[0]:
                label = st.selectbox('打开行业内个股', labels, key=member_key)
            def open_current_member():
                current=state.get(member_key)
                frame=members.assign(个股=members['代码'].astype(str)+' · '+members.get('名称',pd.Series('未命名',index=members.index)).fillna('未命名').astype(str))
                open_stock_widget(frame,field,current,navigation,context_prefix,'行业研究台')
            with actions[1]:
                st.button('打开研究卡', key=f'{prefix}_open_stock', on_click=open_current_member, width='stretch')
            with actions[2]:
                download('导出成分股', quote_export(members, data).to_csv(index=False).encode('utf-8-sig'),
                                   file_name='sector_members.csv', mime='text/csv', key=f'{prefix}_export', width='stretch')

