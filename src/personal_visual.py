"""Compact personal views; existing manual allocation rules remain authoritative."""
import streamlit as st
import plotly.graph_objects as go
from .calculations import market_regime, market_close_summary


def slot_range_figure(rows, total):
    """Six shared-scale lanes: a reference band and an actual-position dot."""
    fig = go.Figure()
    actual = [row['实际占比'] if total > 0 else 0 for row in rows]
    upper = max([.30] + [value * 1.15 for value in actual])
    labels = []
    for index, row in enumerate(rows):
        low, high = [float(value.strip().rstrip('%')) / 100
                     for value in row['目标区间'].split('–')]
        fig.add_shape(type='rect', x0=low, x1=high, y0=index-.13,
                      y1=index+.13, fillcolor='#3598b5', line_width=0)
        pending = row['股票'] == '—' and row['当前市值'] == 0
        labels.append('待配置' if pending else
                      ('总资产待填写' if total <= 0 else f"实际 {actual[index]:.1%}"))
    fig.add_scatter(x=actual, y=list(range(len(rows))), mode='markers+text',
                    marker=dict(size=13, color='#ef6c64'), text=labels,
                    textposition='top right', customdata=[
                        [row['股票'], row['当前市值'], row['目标区间']] for row in rows],
                    hovertemplate='%{customdata[0]}<br>市值 %{customdata[1]:,.0f} 元'
                                  '<br>参考 %{customdata[2]}<extra></extra>')
    fig.update_layout(height=360, margin=dict(l=10,r=80,t=20,b=40),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(color='#e7edf7',size=14), showlegend=False,
                      xaxis=dict(range=[-.02,upper+.04],tickformat='.0%',
                                 title='占总资产比例',fixedrange=True),
                      yaxis=dict(tickmode='array',tickvals=list(range(len(rows))),
                                 ticktext=[f"{row['槽位']} · {row['目标区间']}" for row in rows],
                                 range=[len(rows)-.5,-.6],fixedrange=True))
    return fig


def stage_cards(score):
    current = market_regime(score)['name']
    cards = []
    for representative in (0, 2, 3, 5):
        rule = market_regime(representative)
        cards.append(dict(name=rule['name'], active=rule['name'] == current,
                          range=f"{rule['total_low']:.0%}–{rule['total_high']:.0%}",
                          attack=rule['attack_max'], cash=rule['cash']))
    return cards


def render_stage_cards(score):
    for column, item in zip(st.columns(4), stage_cards(score)):
        with column.container(border=True):
            st.badge('当前人工阶段' if item['active'] else '参考阶段',
                     color='red' if item['active'] else 'gray')
            st.markdown(f"### {item['name']}")
            st.metric('总仓参考', item['range'])
            st.caption(f"进攻上限 {item['attack']:.0%} · 现金底线 {item['cash']:.0%}")


def render_allocation(total, attack, defense, cash):
    fig = go.Figure()
    for name, ratio, color in [('进攻仓', attack, '#ef6c64'),
                                ('防守仓', defense, '#3598b5'),
                                ('现金', cash, '#d7b356')]:
        fig.add_bar(y=['参考配置'], x=[ratio], name=name, orientation='h',
                    marker_color=color, text=[f'{name} {ratio:.0%}'],
                    textposition='inside', customdata=[total * ratio],
                    hovertemplate='%{text}<br>%{customdata:,.0f} 元<extra></extra>')
    fig.update_layout(barmode='stack', height=150, margin=dict(l=0,r=0,t=8,b=12),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font_color='#e7edf7', showlegend=False,
                      xaxis=dict(range=[0,1], tickformat='.0%', fixedrange=True),
                      yaxis=dict(visible=False, fixedrange=True))
    st.plotly_chart(fig, width='stretch', key='personal_allocation_chart')
    st.caption('区间中值的参考配置，不是实际持仓，也不会自动调整仓位。')


def render_market_context(state):
    data = state.get('data', {})
    close = market_close_summary(data.get('stocks'))
    with st.container(border=True):
        st.caption(f"市场总览背景 · 快照 {data.get('import_date') or '未提供'} · 非实时")
        if close.get('status') == 'no_quote':
            st.markdown('**市场背景待补数据 · 阶段仍由你确认**')
        else:
            st.markdown(f"**{close['status']}** · 上涨占比 {close['advance_ratio']:.0%}")
        st.caption('只引用总览快照；不把市场冷热自动转换为人工阶段，不修改六项评分。')


def render_position_comparison(actual, stage, total):
    if total <= 0:
        st.caption('总资产为0，无法比较实际仓位与目标区间。')
        return
    upper = max(1, actual * 1.1)
    fig = go.Figure(go.Scatter(x=[actual], y=[0], mode='markers+text',
                              marker=dict(size=18,color='#ef6c64'),
                              text=[f'实际 {actual:.1%}'], textposition='top center'))
    fig.add_vrect(x0=stage['total_low'], x1=stage['total_high'],
                  fillcolor='#3598b5', opacity=.3, line_width=0)
    fig.update_layout(height=150, margin=dict(l=20,r=30,t=30,b=30),
                      showlegend=False, paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)', font_color='#e7edf7',
                      xaxis=dict(range=[-.04,upper+.04],tickformat='.0%',fixedrange=True),
                      yaxis=dict(range=[-.5,.5],visible=False,fixedrange=True))
    st.caption(f"蓝色带：阶段参考 {stage['total_low']:.0%}–{stage['total_high']:.0%} · 红点：当前录入仓位")
    st.plotly_chart(fig, width='stretch', key='personal_actual_target')
