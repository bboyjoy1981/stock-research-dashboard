"""Compact industry/subindustry market map; never creates stock tiles."""
import plotly.express as px


def industry_cloud_figure(frame, path, height=720, color_range=(-3, 3)):
    tree = px.treemap(frame, path=path, values='面积', color='云图颜色',
                      custom_data=['成分股数', '涨跌幅'],
                      range_color=list(color_range),
                      color_continuous_scale=[[0, '#089447'], [.333, '#16613b'],
                                              [.499, '#48494f'], [.501, '#48494f'],
                                              [.667, '#863134'], [1, '#d83a3f']])
    tree.update_traces(hovertemplate='<b>%{label}</b><br>面积指标值：%{value:,.0f}<br>成分股：%{customdata[0]:,.0f} 只<br>平均涨跌：%{customdata[1]:+.2f}%<extra></extra>',
                       texttemplate='%{label}', textfont=dict(size=12, color='#f5f5f5'),
                       marker=dict(line=dict(width=1, color='#101117')),
                       tiling=dict(pad=2, packing='squarify'),
                       pathbar=dict(visible=False), root=dict(color='#101117'))
    tree.update_layout(height=height, margin=dict(t=0, l=0, r=0, b=0),
                       paper_bgcolor='#101117', plot_bgcolor='#101117',
                       coloraxis_showscale=False,
                       font=dict(family='Microsoft YaHei, sans-serif', color='#f5f5f5'))
    return tree
