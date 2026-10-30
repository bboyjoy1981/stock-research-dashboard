"""Original tracked capital-flow labels; no source fetching."""
import unicodedata
import pandas as pd


CAPITAL_FLOW_SECTORS = [
    "电力", "半导体", "通信设备", "计算机设备", "机器人概念", "光伏设备",
    "AIGC概念", "软件开发", "游戏", "工业金属", "小金属", "消费电子", "电池",
    "白酒Ⅱ", "证券Ⅱ", "银行Ⅱ", "商业航天", "军工", "创新药",
]

_SECTOR_ALIASES = {
    "电力": ("电力", "电力行业"),
    "半导体": ("半导体",),
    "通信设备": ("通信设备",),
    "计算机设备": ("计算机设备",),
    "机器人概念": ("机器人概念", "机器人"),
    "光伏设备": ("光伏设备",),
    "AIGC概念": ("AIGC概念", "AIGC"),
    "软件开发": ("软件开发",),
    "游戏": ("游戏", "游戏Ⅱ"),
    "工业金属": ("工业金属", "工业金属概念"),
    "小金属": ("小金属", "小金属概念"),
    "消费电子": ("消费电子", "消费电子概念"),
    "电池": ("电池", "电池概念"),
    "白酒Ⅱ": ("白酒Ⅱ", "白酒II", "白酒概念", "白酒"),
    "证券Ⅱ": ("证券Ⅱ", "证券II", "证券", "券商信托"),
    "银行Ⅱ": ("银行Ⅱ", "银行II", "银行"),
    "商业航天": ("商业航天", "商业航天概念"),
    "军工": ("军工", "军工概念", "国防军工"),
    "创新药": ("创新药", "创新药概念"),
}

def _normalized_label(name: str) -> str:
    return "".join(unicodedata.normalize("NFKC", str(name)).split()).casefold()

def canonical_capital_flow_sector(name: str) -> str | None:
    """Map an Eastmoney industry/concept board label to a tracked display name."""
    if pd.isna(name):
        return None
    label = _normalized_label(name)
    for sector, aliases in _SECTOR_ALIASES.items():
        if label in {_normalized_label(alias) for alias in aliases}:
            return sector
    return None

