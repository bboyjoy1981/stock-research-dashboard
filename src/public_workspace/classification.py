"""Industry browsing and non-exclusive, evidence-labelled research themes."""
import math
import pandas as pd
import streamlit as st
from .reference_model import GROUPS
from ..technology_references import REFERENCES, CHECKED_ON


# Labels describe research filters, not verified business exposure or official indices.
THEMES = {
    'CPO / 光通信': {'CPO': ('CPO',), '光模块': ('光模块',), '光芯片 / 器件': ('光芯片', '光器件'), '光连接与配套': ('光连接', '光纤', '光缆'), '光通信（未细分）': ('光通信',)},
    'PCB': {title: () for title, _, _ in GROUPS},
    '半导体': {'芯片设计': ('芯片设计', '集成电路设计'), '晶圆制造': ('晶圆制造', '芯片制造'), '封装测试': ('封装', '封测'), '半导体设备': ('半导体设备',), '半导体材料': ('半导体材料',), '功率 / 分立器件': ('功率半导体', '分立器件'), '半导体（未细分）': ('半导体', '集成电路')},
    '存储': {'DRAM': ('DRAM',), 'NAND / 闪存': ('NAND', '闪存'), '存储芯片': ('存储芯片',), '存储模组': ('存储模组', '内存条'), '存储控制器': ('存储控制',)},
    '算力基础设施': {'AI 芯片 / GPU': ('GPU', 'AI芯片', 'AI 芯片'), '服务器': ('服务器',), '网络设备': ('交换机', '网络设备'), '液冷': ('液冷',), '数据中心': ('数据中心', 'IDC'), '电源 / 配电': ('服务器电源', 'UPS', '数据中心配电')},
    '软件 / AI 应用': {'基础软件': ('基础软件', '操作系统', '数据库'), '工业软件': ('工业软件',), '企业软件': ('企业软件',), 'AI 应用': ('AI应用', 'AI 应用', '人工智能'), '软件（未细分）': ('软件',)},
    '消费电子': {'终端': ('消费电子', '智能终端'), '电子零部件': ('电子零部件', '连接器'), '光学 / 显示': ('光学', '显示', '面板')},
    '机器人': {'减速器': ('减速器',), '伺服 / 电机': ('伺服', '电机'), '传感器': ('传感器',), '机器人本体': ('机器人本体',), '系统集成': ('机器人集成',), '机器人（未细分）': ('机器人',)},
    '低空经济': {'无人机': ('无人机',), 'eVTOL': ('EVTOL',), '空管 / 导航': ('空管', '低空导航'), '低空运营': ('低空运营',), '低空经济（未细分）': ('低空经济',)},
    '商业航天': {'火箭 / 发射': ('火箭', '发射服务'), '卫星制造': ('卫星制造',), '卫星通信': ('卫星通信',), '遥感 / 导航': ('遥感', '卫星导航'), '商业航天（未细分）': ('商业航天',)},
    '国产替代': {'信创': ('信创',), '自主可控': ('自主可控',), '国产替代（未细分）': ('国产替代',)},
}
THEMES['存储']['NOR Flash'] = ('NOR FLASH',)
THEMES['存储']['内存接口 / 配套芯片'] = ('内存接口', '内存模组配套芯片')
# A broad tag may also match a precise layer; do not label that overlap "unclassified".
THEMES = {
    theme: {name.replace('（未细分）', '（泛标签匹配）'): words for name, words in layers.items()}
    for theme, layers in THEMES.items()
}


@st.cache_data(max_entries=8, show_spinner=False)
def prepare_stocks(stocks):
    frame = stocks.loc[:, ~stocks.columns.duplicated()].copy()
    for field in ('代码', '名称'):
        if field not in frame:
            frame[field] = pd.Series(index=frame.index, dtype=str)
    frame['代码'] = frame['代码'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(6)
    frame = frame.loc[frame['代码'].str.fullmatch(r'\d{6}')].drop_duplicates('代码', keep='last')
    industry = frame['行业'] if '行业' in frame else pd.Series(index=frame.index, dtype=str)
    frame['浏览行业'] = industry.fillna('').astype(str).str.strip().replace('', '未分类')
    if '细分行业' in frame:
        frame['细分行业'] = frame['细分行业'].fillna('').astype(str).str.strip().replace('', '未细分')
    return frame


def industry_members(frame, industry, layer='全部'):
    result = frame if industry == '全部行业' else frame.loc[frame['浏览行业'].eq(industry)]
    if layer != '全部' and '细分行业' in result:
        result = result.loc[result['细分行业'].fillna('未细分').astype(str).eq(layer)]
    return result.copy()


def theme_members(frame, theme, layer='全部'):
    fields = [f for f in ('行业', '细分行业', '标签', '概念') if f in frame]
    text = frame[fields].fillna('').astype(str).agg(' '.join, axis=1).str.upper() if fields else pd.Series('', index=frame.index)
    mask = pd.Series(False, index=frame.index)
    rules = THEMES.get(theme, {})
    for name, words in rules.items():
        if layer not in ('全部', name):
            continue
        for word in words:
            mask |= text.str.contains(word.upper(), regex=False)
    reference = pd.Series(False, index=frame.index)
    if theme == 'PCB':
        codes = [code for title, _, entries in GROUPS if layer in ('全部', title) for _, code in entries]
        reference = frame['代码'].isin(codes)
        if layer == '全部':
            mask |= text.str.contains('PCB|印制电路板|覆铜板', regex=True)
        mask |= reference
    evidence = {}
    for code, direction, node, url, note in REFERENCES:
        if direction == theme and layer in ('全部', node):
            mask |= frame['代码'].eq(code)
            evidence.setdefault(code, []).append((node, url, note))
    result = frame.loc[mask].copy()
    result['分类依据'] = '导入行业 / 标签匹配 · 待逐股核验'
    result.loc[reference.loc[result.index], '分类依据'] = 'PCB 参考名单 · 研究分层'
    result['归属来源'] = ''
    result['归属核对日期'] = ''
    result['归属说明'] = ''
    result['归属证据'] = pd.Series([[] for _ in range(len(result))], index=result.index, dtype=object)
    for code, items in evidence.items():
        match = result['代码'].eq(code)
        result.loc[match, '分类依据'] = '公司官网 / 公告产品依据 · 研究归类'
        result.loc[match, '归属来源'] = items[0][1]
        result.loc[match, '归属核对日期'] = CHECKED_ON
        result.loc[match, '归属说明'] = '；'.join(f'{node}：{note}' for node, _, note in items)
        for index in result.index[match]:
            result.at[index, '归属证据'] = list(items)
    return result


def _number(row, field, percent=False):
    value = pd.to_numeric(row.get(field), errors='coerce')
    if pd.isna(value) or not math.isfinite(float(value)):
        return '—'
    return f'{value:+.2f}%' if percent else f'{value:.2f}'
