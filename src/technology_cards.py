"""Snapshot-only technology grouping and honest quote-card facts."""
import math
import pandas as pd

from .public_workspace.reference_model import GROUPS

# Research navigation, not an official industry or verified constituent feed.
TECHNOLOGY_TAXONOMY = {
    '半导体': ['芯片设计', '晶圆制造', '封装测试', '半导体设备', '半导体材料', '存储芯片'],
    '光通信 / CPO': ['光模块', '光芯片 / 器件', '光连接与配套', 'CPO（需单独核验）'],
    '算力基础设施': ['服务器', '网络设备', '液冷', '数据中心'],
    'PCB': [title for title, _, _ in GROUPS],
    '软件 / AI 应用': ['基础软件', '工业软件', '企业软件', 'AI 应用（需单独核验）'],
    '机器人与智能装备': ['核心零部件', '机器人本体', '系统集成'],
    '消费电子与智能终端': ['终端', '电子零部件', '光学与显示'],
    '生物医药科技': ['创新药（需单独核验）', '研发服务', '生命科学工具'],
    '商业航天与卫星': ['运载火箭与发射服务', '卫星制造与核心部件', '卫星通信与地面设备', '遥感 / 导航 / 数据应用'],
}


def classify_technology(stocks):
    result = stocks.loc[:, ~stocks.columns.duplicated()].copy()
    reference = {code: title for title, _, entries in GROUPS for _, code in entries}
    rules = [
        ('PCB', ('PCB', '印制电路板', '覆铜板')),
        ('光通信 / CPO', ('CPO', '光模块', '光通信', '光器件')),
        ('半导体', ('半导体', '集成电路', '芯片设计', '分立器件', '存储芯片', 'DRAM', 'NAND', 'GPU')),
        ('算力基础设施', ('算力', '服务器', '数据中心', '液冷')),
        ('软件 / AI 应用', ('软件', 'AI应用', 'AI 应用')),
        ('消费电子与智能终端', ('消费电子', '光学光电子', '面板', '光学元件')),
        ('机器人与智能装备', ('机器人', '减速器', '伺服')),
        ('生物医药科技', ('创新药', '医疗研发外包', '生命科学工具')),
        ('商业航天与卫星', ('商业航天', '卫星', '运载火箭')),
    ]
    fields = [field for field in ('行业', '细分行业', '标签', '概念') if field in result]
    records = []
    for _, row in result.iterrows():
        code = str(row.get('代码', '')).removesuffix('.0').zfill(6)
        layer = reference.get(code)
        if layer:
            records.append(('PCB', layer, '用户参考名单 · 研究分层，非当前业务核验'))
            continue
        text = ' '.join(str(row[field]) for field in fields if pd.notna(row[field])).upper()
        category = next((name for name, words in rules if any(word.upper() in text for word in words)), '其他 / 未分类')
        fine = row.get('细分行业', row.get('行业', '未细分'))
        fine = str(fine) if pd.notna(fine) and str(fine).strip() else '未细分'
        records.append((category, fine, '导入行业 / 标签关键词 · 研究归类' if category != '其他 / 未分类' else '未识别科技归属'))
    result[['科技方向', '科技细分', '分类依据']] = pd.DataFrame(records, index=result.index, columns=['科技方向', '科技细分', '分类依据'])
    return result


def price_range(row):
    def number(fields):
        for field in fields:
            value = pd.to_numeric(row.get(field), errors='coerce')
            if pd.notna(value) and math.isfinite(float(value)) and value > 0:
                return float(value)
        return None
    low, high, current = number(('最低', '最低价')), number(('最高', '最高价')), number(('价格',))
    if low is None or high is None or current is None or high <= low or not low <= current <= high:
        return None
    return low, high, (current - low) / (high - low)
