from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class MarketSnapshot:
    name: str
    value: float
    change_pct: float
    score: int = 0


@dataclass
class SectorRow:
    name: str
    change_pct: float
    turnover: float
    leader: str


@dataclass
class StockRow:
    code: str
    name: str
    sector: str
    price: float
    change_pct: float
    score: int
    risk_score: int
    turnover: float = 0.0
    tags: str = ""


@dataclass
class PositionRow:
    slot: str
    role: str
    code: str = ""
    name: str = ""
    actual_value: float = 0.0
    low: float = 0.0
    high: float = 0.0


@dataclass
class TradePlan:
    trade_date: str
    code: str
    name: str
    horizon: str
    thesis: str
    invalidation: str
    planned_weight: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    review: str = ""


@dataclass
class TradeRecord:
    trade_date: str
    code: str
    name: str
    action: str
    price: float
    quantity: int
    fee: float = 0.0
    note: str = ""
