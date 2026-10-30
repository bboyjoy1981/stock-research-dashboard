import sqlite3
from .models import TradePlan, TradeRecord


def init_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS trade_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT, code TEXT, name TEXT,
            horizon TEXT, thesis TEXT, invalidation TEXT, planned_weight REAL,
            stop_loss REAL, take_profit REAL, review TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT NOT NULL, positions_json TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS market_snapshots (
            trade_date TEXT PRIMARY KEY, payload_json TEXT NOT NULL, saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS trade_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT, code TEXT, name TEXT,
            action TEXT, price REAL, quantity INTEGER, fee REAL, note TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS theme_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT, theme TEXT,
            payload_json TEXT NOT NULL, saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def save_market_snapshot(path: str, trade_date: str, payload: dict) -> None:
    import json
    init_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO market_snapshots(trade_date,payload_json) VALUES(?,?) "
            "ON CONFLICT(trade_date) DO UPDATE SET payload_json=excluded.payload_json,saved_at=CURRENT_TIMESTAMP",
            (trade_date, json.dumps(payload, ensure_ascii=False)),
        )


def list_market_snapshots(path: str, limit: int = 30) -> list[dict]:
    import json
    init_db(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT trade_date,payload_json,saved_at FROM market_snapshots ORDER BY trade_date DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [{"trade_date": date, **json.loads(payload), "saved_at": saved_at} for date, payload, saved_at in rows]


def save_portfolio_snapshot(path: str, trade_date: str, positions: list[dict]) -> int:
    import json
    init_db(path)
    with sqlite3.connect(path) as conn:
        cur = conn.execute("INSERT INTO portfolio_snapshots(trade_date,positions_json) VALUES(?,?)", (trade_date, json.dumps(positions, ensure_ascii=False)))
        return int(cur.lastrowid)


def list_portfolio_snapshots(path: str) -> list[dict]:
    import json
    init_db(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT trade_date,positions_json FROM portfolio_snapshots ORDER BY id DESC").fetchall()
    return [{"trade_date": date, "positions": json.loads(payload)} for date, payload in rows]


def save_trade_plan(path: str, plan: TradePlan) -> int:
    init_db(path)
    with sqlite3.connect(path) as conn:
        cur = conn.execute("INSERT INTO trade_plans(trade_date,code,name,horizon,thesis,invalidation,planned_weight,stop_loss,take_profit,review) VALUES(?,?,?,?,?,?,?,?,?,?)", tuple(plan.__dict__.values()))
        return int(cur.lastrowid)


def list_trade_plans(path: str) -> list[TradePlan]:
    init_db(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT trade_date,code,name,horizon,thesis,invalidation,planned_weight,stop_loss,take_profit,review FROM trade_plans ORDER BY id DESC").fetchall()
    return [TradePlan(*row) for row in rows]


def save_trade_record(path: str, record: TradeRecord) -> int:
    init_db(path)
    with sqlite3.connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO trade_records(trade_date,code,name,action,price,quantity,fee,note) VALUES(?,?,?,?,?,?,?,?)",
            tuple(record.__dict__.values()),
        )
        return int(cur.lastrowid)


def list_trade_records(path: str, limit: int = 500) -> list[TradeRecord]:
    init_db(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT trade_date,code,name,action,price,quantity,fee,note FROM trade_records ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [TradeRecord(*row) for row in rows]


def save_theme_snapshot(path: str, trade_date: str, theme: str, payload: dict) -> int:
    import json
    init_db(path)
    with sqlite3.connect(path) as conn:
        cur = conn.execute("INSERT INTO theme_snapshots(trade_date,theme,payload_json) VALUES(?,?,?)", (trade_date, theme, json.dumps(payload, ensure_ascii=False)))
        return int(cur.lastrowid)


def list_theme_snapshots(path: str, limit: int = 50) -> list[dict]:
    import json
    init_db(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT trade_date,theme,payload_json,saved_at FROM theme_snapshots ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [{"trade_date": d, "theme": t, **json.loads(payload), "saved_at": saved} for d, t, payload, saved in rows]
