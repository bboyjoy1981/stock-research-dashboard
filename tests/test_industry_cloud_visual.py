import pandas as pd


def test_industry_cloud_groups_subindustries_without_stock_tiles():
    from src.industry_cloud import industry_cloud_figure
    frame = pd.DataFrame({'行业': ['电子', '电子', '通信'], '细分行业': ['芯片', 'PCB', '设备'],
                          '面积': [10, 20, 30], '涨跌幅': [1, -2, 0], '云图颜色': [1, -2, 0], '成分股数': [2, 3, 4]})
    fig = industry_cloud_figure(frame, ['行业', '细分行业'], height=600)
    assert set(fig.data[0].parents) >= {'电子', '通信'}
    assert fig.layout.height == 600
    assert fig.layout.paper_bgcolor == '#101117'
    assert len(fig.data[0].labels) == 5
