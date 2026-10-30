"""Original K-line figure and controls over explicitly supplied OHLCV only."""
import pandas as pd
import streamlit as st
from ..daily_model import aggregate_stock_bars,DAILY_COLUMNS
from ..components import public_table


def render(dataset,code,capabilities,state,prefix='',through_date=None):
    st.subheader('个股 K 线',icon=':material/candlestick_chart:')
    if dataset is None or dataset.frame.empty:
        st.info('日线历史尚未发布；收盘快照不替代日线或分钟走势。')
        return
    if not isinstance(code,str) or len(code)!=6 or not code.isascii() or not code.isdigit():
        st.warning('股票代码无效。')
        return
    if dataset.kind!='daily_history': raise ValueError('Explicit daily history required')
    frame=dataset.frame.loc[dataset.frame['代码'].eq(code)].copy()
    if through_date:
        frame=frame.loc[frame['交易日'].le(through_date)]
    range_col,period_col,adjustment_col=st.columns([1.8,1.15,1.4],vertical_alignment='bottom')
    with range_col:
        display_range=st.segmented_control('显示区间',['3个月','6个月','1年','3年'],default='1年',key=prefix+f'stock_daily_range_{code}') or '1年'
    with period_col:
        period=st.segmented_control('K线周期',['日K','周K','月K'],default='日K',key=prefix+f'stock_kline_period_{code}') or '日K'
    with adjustment_col:
        adjustment=st.segmented_control('复权方式',['前复权','不复权'],default='前复权',key=prefix+f'stock_daily_adjustment_{code}') or '前复权'
    if display_range not in ('3个月','6个月','1年','3年') or period not in ('日K','周K','月K') or adjustment not in ('前复权','不复权'):
        st.warning('日线选项无效。')
        return
    frame=frame.loc[frame['复权方式'].eq(adjustment)]
    if frame.empty:
        st.warning('所选股票、复权口径或回放日期没有已发布日线；不替换成其他口径。')
        return
    units=frame['成交量单位'].dropna().unique()
    if len(units)!=1:
        st.warning('成交量单位不一致，暂不绘制跨单位曲线。')
        return
    st.caption(f"成交量单位：{units[0]}；不自动换算股/手。日线来源日期：{dataset.metadata['date']}。")
    metadata=dict(source=dataset.metadata['source'],last_trade_date=frame['交易日'].max(),fetched_at='未提供')
    render_chart(frame[DAILY_COLUMNS],metadata,None,code,adjustment,period,display_range,
        capabilities,prefix,anchor=through_date or dataset.metadata['date'])


def render_chart(daily_bars,daily_metadata,daily_error,selected_code,adjustment,kline_period,display_range,capabilities,prefix='',anchor=None):
    def table(frame,**kwargs):
        return public_table(frame,(*DAILY_COLUMNS,'MA5','MA10','MA20','MA60'),capabilities,**kwargs)
    period_bars = aggregate_stock_bars(daily_bars, kline_period)
    if daily_error:
        st.warning(f"自动更新失败，当前展示本地缓存（最近交易日 {daily_bars.iloc[-1]['交易日']}）。数据源提示：{daily_error}")
    else:
        st.caption(
            f"数据源：{daily_metadata.get('source', '本地缓存')}｜"
            f"最近交易日：{daily_metadata.get('last_trade_date', daily_bars.iloc[-1]['交易日'])}｜"
            f"本地抓取时间：{daily_metadata.get('fetched_at', '未知')}"
        )
    range_days = {'3个月': 92, '6个月': 183, '1年': 365, '3年': 365 * 3}[display_range]
    chart_start = ((pd.Timestamp(anchor).normalize() if anchor else pd.Timestamp.now().normalize()) - pd.Timedelta(days=range_days)).strftime('%Y-%m-%d')
    visible_bars = period_bars.loc[period_bars['交易日'].ge(chart_start)].copy()
    if visible_bars.empty:
        st.info('所选区间内暂时没有有效交易日数据。')
    else:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        chart_bars = period_bars.copy()
        for window in (5, 10, 20, 60):
            chart_bars[f'MA{window}'] = chart_bars['收盘'].rolling(window, min_periods=window).mean()
        chart_bars = chart_bars.loc[chart_bars['交易日'].ge(chart_start)].copy()
        candle_colors = [
            '#ef5350' if close >= open_price else '#22c55e'
            for open_price, close in zip(chart_bars['开盘'], chart_bars['收盘'])
        ]
        figure = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.035,
            row_heights=[0.72, 0.28],
        )
        figure.add_trace(go.Candlestick(
            x=chart_bars['交易日'], open=chart_bars['开盘'], high=chart_bars['最高'],
            low=chart_bars['最低'], close=chart_bars['收盘'], name=kline_period,
            increasing_line_color='#ef5350', decreasing_line_color='#22c55e',
            increasing_fillcolor='#ef5350', decreasing_fillcolor='#22c55e',
        ), row=1, col=1)
        ma_colors = {'MA5': '#f6c85f', 'MA10': '#6f4e7c', 'MA20': '#9fd356', 'MA60': '#ca472f'}
        for ma_name, color in ma_colors.items():
            figure.add_trace(go.Scatter(
                x=chart_bars['交易日'], y=chart_bars[ma_name], mode='lines',
                name=ma_name, line={'width': 1.2, 'color': color},
            ), row=1, col=1)
        figure.add_trace(go.Bar(
            x=chart_bars['交易日'], y=chart_bars['成交量'], name='成交量',
            marker_color=candle_colors,
        ), row=2, col=1)
        figure.update_layout(
            template='plotly_dark', height=590, margin={'l': 12, 'r': 12, 't': 28, 'b': 10},
            paper_bgcolor='#0b111b', plot_bgcolor='#0b111b',
            legend={'orientation': 'h', 'y': 1.02, 'x': 0},
            xaxis_rangeslider_visible=False,
        )
        figure.update_yaxes(title_text='价格', row=1, col=1, fixedrange=False)
        figure.update_yaxes(title_text='成交量（源单位）', row=2, col=1, fixedrange=False)
        figure.update_xaxes(type='category', rangeslider_visible=False, row=1, col=1)
        figure.update_xaxes(type='category', row=2, col=1)
        st.plotly_chart(figure, width='stretch', key=prefix+f'stock_daily_chart_{selected_code}_{adjustment}_{kline_period}')
        with st.expander(f'查看{kline_period}线明细'):
            table(visible_bars, width='stretch', hide_index=True)


