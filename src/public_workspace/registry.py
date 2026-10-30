"""Explicit public route allowlist; never import the owner page registry."""
from importlib import import_module
from types import MappingProxyType

_ROUTES=MappingProxyType({
    '市场总览':'overview',
    '大盘云图':'cloud',
    '板块资金流向':'capital',
    '指数分析':'index_analysis',
    '概念排行':'concepts',
    '盘中选股':'scanner',
    '板块热力图':'heatmap',
    '产业链分层':'industry_chain',
    '热点舆情':'news',
    '个股详情':'stock_detail',
    '板块细分':'sector_directory',
})
PAGES=tuple(_ROUTES)


def render_page(page,snapshot,capabilities,navigation):
    if not isinstance(page,str) or page not in _ROUTES:
        raise ValueError('Unsupported public page')
    if page not in navigation.allowed_pages:
        raise ValueError('Public navigation does not allow this page')
    module=import_module('.pages.'+_ROUTES[page],__package__)
    return module.render(snapshot,capabilities,navigation)
