from io import BytesIO
import pandas as pd
from pathlib import Path
from datetime import datetime
import re


def _parse_ths_text(file_bytes: bytes) -> pd.DataFrame:
    text = None
    for encoding in ("gb18030", "utf-8-sig", "utf-8"):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("无法识别 TXT 文件编码")
    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        header = lines[0].split("\t")
        compact_header = [cell.strip() for cell in header if cell.strip()]
        quote_layout = compact_header[:4] == ['.', '代码', '名称', '.']
        if quote_layout:
            # The blank status column after the name has no data token.
            header = compact_header[:3] + compact_header[4:]
        if any(cell.strip() == "\u4ee3\u7801" for cell in header) and any(cell.strip() == "\u540d\u79f0" for cell in header):
            header_to_field = {
                "\u6da8\u5e45": "\u6da8\u8dcc\u5e45", "\u73b0\u4ef7": "\u4ef7\u683c",
                "\u603b\u91d1\u989d": "\u6210\u4ea4\u989d", "\u6362\u624b": "\u6362\u624b\u7387",
                "\u603b\u624b": "\u6210\u4ea4\u91cf", "\u6240\u5c5e\u884c\u4e1a": "\u884c\u4e1a",
                "\u7ec6\u5206\u884c\u4e1a": "\u7ec6\u5206\u884c\u4e1a", "\u91cf\u6bd4": "\u91cf\u6bd4",
            }
            parsed_rows = []
            header_to_field.update({"昨收": "昨收", "昨收价": "昨收", "前收盘价": "昨收",
                                    "今开": "今开", "开盘价": "今开", "开盘": "今开",
                                    "最高": "最高", "最高价": "最高", "最低": "最低", "最低价": "最低"})
            header_to_field.update({'总市值': '总市值', '流通市值': '流通市值'})
            for line in lines[1:]:
                cells = line.split("\t")
                if quote_layout:
                    cells = [cell.strip() for cell in cells if cell.strip()]
                code_idx = next((i for i, cell in enumerate(cells) if re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", cell.strip(), re.I)), None)
                if code_idx is None:
                    continue
                symbol = cells[code_idx].strip().upper()
                digits = symbol[-6:]
                name = next((cell.strip() for cell in cells[code_idx + 1:] if re.search(r"[\u4e00-\u9fff]", cell)), digits)
                board = "\u79d1\u521b\u677f" if digits.startswith("688") else "\u521b\u4e1a\u677f" if digits.startswith(("300", "301")) else "\u5317\u4ea4\u6240" if digits.startswith(("43", "83", "87")) else "\u4e3b\u677f"
                item = {"\u4ee3\u7801": digits, "\u540d\u79f0": name, "\u677f\u5757": board}
                for h_idx, label in enumerate(header):
                    field = header_to_field.get(label.strip())
                    value_idx = h_idx if quote_layout else (h_idx - 2 if h_idx >= 8 else h_idx)
                    if field and value_idx < len(cells):
                        value = cells[value_idx].strip()
                        if value:
                            item[field] = value
                parsed_rows.append(item)
            if parsed_rows:
                parsed = pd.DataFrame(parsed_rows).drop_duplicates("\u4ee3\u7801")
                if '总手' in [label.strip() for label in header] and '成交量' in parsed:
                    parsed['成交量源字段'] = '总手'
                for col in ("\u4ef7\u683c", "\u6da8\u8dcc\u5e45", "\u6362\u624b\u7387", "\u91cf\u6bd4"):
                    if col in parsed:
                        parsed[col] = pd.to_numeric(parsed[col].astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False), errors="coerce")
                for col in ("\u6210\u4ea4\u989d", "\u6210\u4ea4\u91cf", "总市值", "流通市值"):
                    if col in parsed:
                        def to_scaled(value):
                            match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*(\u4ebf|\u4e07|\u5143)?\s*", str(value))
                            if not match:
                                return pd.NA
                            scale = {"\u4ebf": 1e8, "\u4e07": 1e4, "\u5143": 1, None: 1}[match.group(2)]
                            return float(match.group(1)) * scale
                        parsed[col] = parsed[col].map(to_scaled)
                return parsed
    rows = []
    for line in text.splitlines():
        match = re.search(r"(?<!\d)(?:(?:SH|SZ|BJ)\d{6}|\d{6})(?!\d)", line, re.I)
        if not match:
            continue
        code = match.group(0).upper()
        digits = code[-6:]
        tail = line[match.end():].strip()
        name_match = re.search(r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9*·-]{1,15}", tail)
        name = name_match.group(0) if name_match else digits
        board = "科创板" if digits.startswith("688") else "创业板" if digits.startswith(("300", "301")) else "北交所" if digits.startswith(("43", "83", "87")) else "主板"
        rows.append({"代码": digits, "名称": name, "板块": board})
    result = pd.DataFrame(rows).drop_duplicates("代码")
    if result.empty:
        raise ValueError("没有识别到股票代码，请确认导出范围包含股票代码")
    return result


def read_tabular_upload(file_bytes: bytes, filename: str) -> pd.DataFrame:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(BytesIO(file_bytes), sep=None, engine="python", encoding_errors="ignore")
    if lower.endswith((".txt", ".text")):
        return _parse_ths_text(file_bytes)
    if lower.endswith(".xlsx"):
        try:
            return pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
        except Exception as exc:
            # Some market terminals export legacy BIFF data with an .xlsx suffix.
            try:
                return pd.read_excel(BytesIO(file_bytes), engine="xlrd")
            except Exception:
                raise ValueError("该文件扩展名是 .xlsx，但内部不是标准 Excel 格式。请在同花顺重新导出为 CSV，或用 Excel 另存为标准 .xlsx") from exc
    if lower.endswith(".xls"):
        return pd.read_excel(BytesIO(file_bytes), engine="xlrd")
    raise ValueError("仅支持 CSV、XLSX 或 XLS 文件")


def _validate(df, required, percent_fields=()):
    errors = [f"缺少字段：{field}" for field in required if field not in df.columns]
    for field in percent_fields:
        if field in df.columns and ((df[field] < 0) | (df[field] > 1)).any():
            errors.append(f"字段 {field} 必须在0到1之间")
    return errors


def validate_stock_pool(df):
    errors = _validate(df, ["代码", "名称", "板块"])
    if _contains_demo_quotes(df):
        errors.append("文件包含演示行情，不能保存为真实市场复盘数据。请使用实际导出的行情文件。")
    return errors


def _contains_demo_quotes(df):
    return '行情来源' in df and bool(df['行情来源'].fillna('').astype(str).str.contains('演示|demo', case=False, regex=True).any())


def validate_positions(df):
    return _validate(df, ["槽位", "实际金额", "目标下限", "目标上限"], ["目标下限", "目标上限"])


def save_research_upload(df: pd.DataFrame, directory: str, prefix: str = "research") -> str:
    if _contains_demo_quotes(df):
        raise ValueError("演示行情不能保存为真实市场复盘数据。")
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.csv"
    path = target / filename
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return str(path)


def normalize_stock_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    aliases = {
        "股票代码": "代码", "证券代码": "代码", "名称": "名称", "股票名称": "名称",
        "现价": "价格", "最新价": "价格", "涨幅": "涨跌幅", "涨跌": "涨跌幅",
        "成交额(亿)": "成交额", "成交额": "成交额", "换手率": "换手率",
    }
    # Terminal exports use several equivalent labels for the same field.
    for col in list(df.columns):
        clean = str(col).replace(" ", "")
        if clean in {"股票简称", "证券简称", "证券名称"} or "名称" in clean or "简称" in clean:
            aliases[col] = "名称"
        elif clean in {"细分行业", "所属细分行业", "行业细分", "申万二级行业"}:
            aliases[col] = "细分行业"
        elif clean in {"所属行业", "所属板块", "板块名称", "行业"} or "板块" in clean or "行业" in clean:
            aliases[col] = "板块"
        elif clean in {"股票代码", "证券代码", "代码"} or clean.endswith("代码"):
            aliases[col] = "代码"
        elif clean in {"涨幅", "涨跌幅", "涨跌幅%", "涨跌"}:
            aliases[col] = "涨跌幅"
        elif clean in {"最新", "最新价", "现价", "收盘价", "收盘"}:
            aliases[col] = "价格"
        elif clean in {"成交金额", "成交额", "成交额(元)", "成交额(万元)"}:
            aliases[col] = "成交额"
        elif clean in {"换手", "换手率%", "换手率"}:
            aliases[col] = "换手率"
    out = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns}).copy()
    if "代码" in out.columns:
        out["代码"] = out["代码"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    for col in ["价格", "涨跌幅", "成交额", "换手率", "综合分", "风险分"]:
        if col in out.columns:
            values = out[col].astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
            out[col] = pd.to_numeric(values, errors="coerce").fillna(0)
    return out


def normalize_stock_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize export labels without conflating exchange board and industry."""
    out = df.copy()
    out.columns = [str(col).replace("\ufeff", "").strip() for col in out.columns]
    aliases = {}
    for col in out.columns:
        clean = re.sub(r"\s+", "", str(col))
        exact = {
            "\u80a1\u7968\u4ee3\u7801": "\u4ee3\u7801", "\u8bc1\u5238\u4ee3\u7801": "\u4ee3\u7801", "\u4ee3\u7801": "\u4ee3\u7801",
            "\u80a1\u7968\u540d\u79f0": "\u540d\u79f0", "\u80a1\u7968\u7b80\u79f0": "\u540d\u79f0", "\u8bc1\u5238\u7b80\u79f0": "\u540d\u79f0", "\u540d\u79f0": "\u540d\u79f0",
            "\u6240\u5c5e\u677f\u5757": "\u677f\u5757", "\u677f\u5757\u540d\u79f0": "\u677f\u5757", "\u5e02\u573a\u677f\u5757": "\u677f\u5757", "\u677f\u5757": "\u677f\u5757",
            "\u6240\u5c5e\u884c\u4e1a": "\u884c\u4e1a", "\u884c\u4e1a": "\u884c\u4e1a", "\u7ec6\u5206\u884c\u4e1a": "\u7ec6\u5206\u884c\u4e1a",
            "\u73b0\u4ef7": "\u4ef7\u683c", "\u6700\u65b0\u4ef7": "\u4ef7\u683c", "\u4ef7\u683c": "\u4ef7\u683c",
            "\u6da8\u5e45": "\u6da8\u8dcc\u5e45", "\u6da8\u8dcc\u5e45": "\u6da8\u8dcc\u5e45",
            "\u603b\u91d1\u989d": "\u6210\u4ea4\u989d", "\u6210\u4ea4\u91d1\u989d": "\u6210\u4ea4\u989d", "\u6210\u4ea4\u989d": "\u6210\u4ea4\u989d",
            "\u603b\u624b": "\u6210\u4ea4\u91cf", "\u6210\u4ea4\u91cf": "\u6210\u4ea4\u91cf", "\u6362\u624b": "\u6362\u624b\u7387", "\u6362\u624b\u7387": "\u6362\u624b\u7387",
        }
        exact.update({"昨收价": "昨收", "前收盘价": "昨收", "昨收": "昨收",
                      "开盘价": "今开", "开盘": "今开", "今开": "今开",
                      "最高价": "最高", "最高": "最高", "最低价": "最低", "最低": "最低"})
        if clean in exact:
            aliases[col] = exact[clean]
    out = out.rename(columns=aliases)
    if "\u4ee3\u7801" in out:
        code_digits = (
            out["\u4ee3\u7801"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.extract(r"(\d+)", expand=False)
        )
        out["\u4ee3\u7801"] = code_digits.where(code_digits.str.len().between(1, 6), "").fillna("").str.zfill(6)
        out = out[out["\u4ee3\u7801"].ne("")].drop_duplicates("\u4ee3\u7801").reset_index(drop=True)
    for col in ("\u4ef7\u683c", "\u6da8\u8dcc\u5e45", "\u6362\u624b\u7387", "\u91cf\u6bd4", "\u7efc\u5408\u5206", "\u98ce\u9669\u5206"):
        if col in out:
            out[col] = pd.to_numeric(out[col].astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False), errors="coerce")
    for col in ("昨收", "今开", "最高", "最低"):
        if col in out:
            numbers = pd.to_numeric(out[col].astype(str).str.replace(",", "", regex=False), errors="coerce")
            out[col] = numbers.where(numbers.gt(0))
    for col in ("\u6210\u4ea4\u989d", "\u6210\u4ea4\u91cf"):
        if col in out:
            def scaled(value):
                match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*(\u4ebf|\u4e07|\u5143)?\s*", str(value))
                if not match:
                    return pd.NA
                return float(match.group(1)) * {"\u4ebf": 1e8, "\u4e07": 1e4, "\u5143": 1, None: 1}[match.group(2)]
            out[col] = out[col].map(scaled)
    if "\u540d\u79f0" in out:
        out["\u540d\u79f0"] = out["\u540d\u79f0"].fillna("").astype(str).str.strip()
    for col in ("\u677f\u5757", "\u884c\u4e1a", "\u7ec6\u5206\u884c\u4e1a", "\u6807\u7b7e"):
        if col in out:
            out[col] = out[col].fillna("").astype(str).str.strip()
            if col in ("\u884c\u4e1a", "\u7ec6\u5206\u884c\u4e1a"):
                invalid_label = out[col].str.fullmatch(r"[+-]?\d+(?:\.\d+)?%?", na=False) | out[col].isin({"--", "nan", "None"})
                out.loc[invalid_label, col] = ""
    return out


def select_market_group_column(df: pd.DataFrame, minimum_coverage: float = 0.15) -> str:
    from .public_workspace.scanner_model import select_market_group_column as select
    return select(df,minimum_coverage)


def market_map_hierarchy_path(df: pd.DataFrame, hierarchy: str) -> list[str]:
    from .public_workspace.cloud_model import market_map_hierarchy_path as shared
    return shared(df,hierarchy)


def market_group_display_mask(df: pd.DataFrame, field: str, include_unclassified: bool = False) -> pd.Series:
    from .public_workspace.market_groups import market_group_display_mask as shared
    return shared(df,field,include_unclassified)


def market_group_coverage(df: pd.DataFrame, field: str) -> dict[str, int | float]:
    from .public_workspace.detail_model import market_group_coverage as shared
    return shared(df,field)


def valid_peer_group_fields(df: pd.DataFrame, row_index, candidates: list[str]) -> list[str]:
    from .public_workspace.detail_model import valid_peer_group_fields as shared
    return shared(df,row_index,candidates)


def market_navigation_level(df: pd.DataFrame, group_name: str, fallback: str = "板块") -> str:
    """Choose the most specific available field that contains a selected group."""
    target = str(group_name).strip()
    if not target:
        return fallback
    for field in ("细分行业", "行业", "板块"):
        if field not in df.columns:
            continue
        labels = df[field].fillna("").astype(str).str.strip()
        if bool(labels.eq(target).any()):
            return field
    return fallback


def researchable_market_groups(grouped: pd.DataFrame, minimum_samples: int = 3) -> pd.DataFrame:
    from .public_workspace.market_groups import researchable_market_groups as shared
    return shared(grouped,minimum_samples)


def stock_pool_template() -> pd.DataFrame:
    return pd.DataFrame(columns=["代码", "名称", "板块", "价格", "涨跌幅", "成交额", "换手率", "综合分", "风险分", "标签"])


def capital_replay_template() -> pd.DataFrame:
    from .public_workspace.capital_model import capital_replay_template as shared
    return shared()


def _capital_replay_number(value):
    from .public_workspace.capital_model import _capital_replay_number as shared
    return shared(value)


def normalize_capital_replay(df: pd.DataFrame) -> pd.DataFrame:
    from .public_workspace.capital_model import normalize_capital_replay as shared
    return shared(df)


def validate_capital_replay(df: pd.DataFrame) -> list[str]:
    errors = _validate(df, ["时间", "行业", "净流入额"])
    if "时间" in df.columns and df["时间"].fillna("").astype(str).str.strip().eq("").all():
        errors.append("时间字段没有有效值")
    if "行业" in df.columns and df["行业"].fillna("").astype(str).str.strip().eq("").all():
        errors.append("行业字段没有有效值")
    if "净流入额" in df.columns and pd.to_numeric(df["净流入额"], errors="coerce").notna().sum() == 0:
        errors.append("净流入额字段没有有效数值")
    return errors


def save_capital_replay(df: pd.DataFrame, directory: str) -> str:
    return save_research_upload(normalize_capital_replay(df), directory, "capital_replay")


def load_capital_replay(directory: str) -> pd.DataFrame:
    target = Path(directory)
    files = sorted(target.glob("capital_replay_*.csv")) if target.exists() else []
    if not files:
        return capital_replay_template()
    frames = [normalize_capital_replay(pd.read_csv(file, encoding="utf-8-sig")) for file in files]
    return pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)


def capital_replay_industry_track(df: pd.DataFrame, industry: str) -> pd.DataFrame:
    from .public_workspace.capital_model import capital_replay_industry_track as shared
    return shared(df, industry)


def capital_replay_flow_changes(df: pd.DataFrame) -> pd.DataFrame:
    from .public_workspace.capital_model import capital_replay_flow_changes as shared
    return shared(df)


def capital_replay_readiness(df: pd.DataFrame) -> dict:
    from .public_workspace.capital_model import capital_replay_readiness as shared
    return shared(df)


def filter_capital_replay_by_date(df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    from .public_workspace.capital_model import filter_capital_replay_by_date as shared
    return shared(df, trade_date)


def capital_replay_snapshot_map(df: pd.DataFrame) -> pd.DataFrame:
    from .public_workspace.capital_model import capital_replay_snapshot_map as shared
    return shared(df)


def load_latest_research(directory: str) -> pd.DataFrame | None:
    files = sorted(Path(directory).glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return normalize_stock_columns(pd.read_csv(files[0], encoding="utf-8-sig"))


def load_research_history(directory: str, limit: int = 30) -> pd.DataFrame:
    """Load the most complete quoted market snapshot per trade date."""
    files = sorted(Path(directory).glob("*.csv"), key=lambda path: (path.stat().st_mtime, path.name))
    snapshots = {}
    quote_counts = {}
    for file in files:
        frame = normalize_stock_columns(pd.read_csv(file, encoding="utf-8-sig"))
        if _contains_demo_quotes(frame):
            continue
        if "涨跌幅" not in frame.columns:
            continue
        valid_returns = int(pd.to_numeric(frame["涨跌幅"], errors="coerce").notna().sum())
        if valid_returns == 0:
            continue
        snapshot_date = infer_import_date(frame) or datetime.fromtimestamp(file.stat().st_mtime).date().isoformat()
        frame["快照日期"] = snapshot_date
        # Keep a full-market export when a smaller watchlist is uploaded later.
        # Equal-sized reimports use the newest file.
        if valid_returns >= quote_counts.get(snapshot_date, -1):
            snapshots[snapshot_date] = frame
            quote_counts[snapshot_date] = valid_returns
    if not snapshots:
        return pd.DataFrame(columns=["快照日期"])
    latest_dates = sorted(snapshots)[-max(1, int(limit)):]
    return pd.concat([snapshots[day] for day in latest_dates], ignore_index=True).sort_values("快照日期").reset_index(drop=True)


def available_quote_snapshot_dates(history: pd.DataFrame) -> list[str]:
    """Dates with at least one usable stock return in saved market history."""
    if history is None or history.empty or not {"快照日期", "涨跌幅"}.issubset(history.columns):
        return []
    valid = history.loc[pd.to_numeric(history["涨跌幅"], errors="coerce").notna(), "快照日期"]
    return sorted(valid.dropna().astype(str).str.strip().loc[lambda dates: dates.ne("")].unique().tolist())


def latest_quote_snapshot(history: pd.DataFrame) -> tuple[pd.DataFrame | None, str | None]:
    """Return the latest usable market snapshot independently of watchlist uploads."""
    dates = available_quote_snapshot_dates(history)
    if not dates:
        return None, None
    trade_date = dates[-1]
    return history.loc[history["快照日期"].astype(str).eq(trade_date)].copy(), trade_date


def select_research_snapshot(data: dict, trade_date: str) -> dict:
    """Switch public stock research to one saved date without changing the input."""
    history = data.get("market_history")
    if trade_date not in available_quote_snapshot_dates(history):
        return data
    selected = history.loc[history["快照日期"].astype(str).eq(trade_date)].copy()
    result = dict(data)
    result["stocks"] = selected
    result["import_date"] = trade_date
    result["stock_quote_source"] = "imported"
    result["source_notice"] = f"正在回放 {trade_date} 的导入快照；市场指数仍为演示数据，非实时行情。"
    return result


def import_quality_report(df: pd.DataFrame) -> dict:
    """Describe whether an imported snapshot is safe for decision support."""
    frame = df.copy()
    rows = int(len(frame))
    quote_columns = ["价格", "涨跌幅", "成交额", "换手率", "成交量"]
    coverage = {}
    for field in quote_columns:
        if field not in frame.columns:
            coverage[field] = 0.0
            continue
        values = pd.to_numeric(frame[field], errors="coerce")
        if field == "价格":
            values = values.where(values > 0)
        coverage[field] = float(values.notna().mean()) if rows else 0.0
    valid_quotes = 0
    if {"价格", "涨跌幅"}.issubset(frame.columns):
        price = pd.to_numeric(frame["价格"], errors="coerce")
        change = pd.to_numeric(frame["涨跌幅"], errors="coerce")
        valid_quotes = int((price.gt(0) & change.notna()).sum())
    return {
        "rows": rows,
        "valid_quotes": valid_quotes,
        "coverage": coverage,
        "missing_fields": [field for field, ratio in coverage.items() if ratio == 0],
        "partial_fields": [field for field, ratio in coverage.items() if 0 < ratio < 1],
        "quote_ready": bool(rows and valid_quotes),
    }


def infer_import_date(df: pd.DataFrame):
    """Infer the most common trade date from common export date columns."""
    if df is None or df.empty:
        return None
    for col in ("快照日期", "交易日期", "日期", "自选时间"):
        if col in df.columns:
            values = pd.to_datetime(df[col], errors="coerce").dropna()
            if not values.empty:
                return values.dt.date.mode().iloc[0].isoformat()
    return None
