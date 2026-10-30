"""Industry capital-flow snapshots from Eastmoney or Tonghuashun."""
from __future__ import annotations

from datetime import datetime
from io import StringIO
import math
import re

import requests

import pandas as pd
from bs4 import BeautifulSoup


EASTMONEY_SOURCE_NAME = "东方财富行业/概念资金流"

from .public_workspace.capital_taxonomy import CAPITAL_FLOW_SECTORS, _SECTOR_ALIASES


_BOARD_QUERY_TYPES = (("行业资金流", "m:90 t:2"), ("概念资金流", "m:90 t:3"))
_EASTMONEY_CLIST_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
)
_SECTOR_SOURCE_TYPES = {
    "机器人概念": ("概念资金流",),
    "AIGC概念": ("概念资金流",),
    "创新药": ("概念资金流",),
    "商业航天": ("概念资金流",),
    # Eastmoney lists military-related boards under both industry and concept ranks.
    "军工": ("行业资金流", "概念资金流"),
}


def _normalized_label(name: str) -> str:
    from .public_workspace.capital_taxonomy import _normalized_label as shared
    return shared(name)


def canonical_capital_flow_sector(name: str) -> str | None:
    from .public_workspace.capital_taxonomy import canonical_capital_flow_sector as shared
    return shared(name)


def _normalize_eastmoney_rank(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize AKShare and raw Eastmoney fields into one internal schema."""
    rename = {
        "f12": "代码", "f14": "名称", "f2": "最新价", "f3": "今日涨跌幅",
        "f62": "主力净流入-净额", "f184": "主力净流入-净占比",
        "f128": "今日主力净流入最大股",
        "今日主力净流入-净额": "主力净流入-净额",
        "今日主力净流入-净占比": "主力净流入-净占比",
    }
    out = raw.rename(columns={key: value for key, value in rename.items() if key in raw.columns}).copy()
    return out


def _fetch_eastmoney_rank_direct(sector_type: str, fs: str, page_size: int = 100) -> pd.DataFrame:
    """Fetch all result pages from Eastmoney; fail rather than returning partial data."""
    params = {
        "pn": "1", "pz": str(page_size), "po": "1", "np": "1", "ut": "b2884a393a59ad64002292a3e90d46a5",
        "fltt": "2", "invt": "2", "fid0": "f62", "fs": fs, "stat": "1",
        "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f124,f128,f136,f140,f141,f152",
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
    host_errors = []
    raw = None
    for host in _EASTMONEY_CLIST_HOSTS:
        url = f"{host}/api/qt/clist/get"
        params["pn"] = "1"
        try:
            first_response = requests.get(url, params=params, timeout=(5, 12), headers=headers)
            first_response.raise_for_status()
            first_data = first_response.json().get("data") or {}
            first_items = first_data.get("diff") or []
            if not first_items:
                raise ValueError(f"{sector_type}接口没有返回排行")
            total = pd.to_numeric(first_data.get("total"), errors="coerce")
            page_count = max(1, math.ceil(float(total) / page_size)) if pd.notna(total) else None
            pages = [pd.DataFrame(first_items)]

            page_number = 2
            while (page_number <= page_count) if page_count is not None else len(pages[-1]) >= page_size:
                params["pn"] = str(page_number)
                response = requests.get(url, params=params, timeout=(5, 12), headers=headers)
                response.raise_for_status()
                payload = response.json().get("data") or {}
                items = payload.get("diff") or []
                if not items:
                    if page_count is not None and page_number <= page_count:
                        raise ValueError(f"{sector_type}第 {page_number} / {page_count} 页为空，拒绝保存不完整排行")
                    break
                pages.append(pd.DataFrame(items))
                page_number += 1
            raw = pd.concat(pages, ignore_index=True)
            break
        except Exception as exc:
            host_errors.append(f"{host}: {str(exc)[:140]}")
    if raw is None:
        raise ConnectionError("东方财富排行接口的各备用地址均失败：" + "；".join(host_errors))
    raw = raw.rename(columns={
        "f12": "代码", "f14": "名称", "f2": "最新价", "f3": "今日涨跌幅",
        "f62": "主力净流入-净额", "f184": "主力净流入-净占比",
        "f128": "今日主力净流入最大股",
    })
    if "代码" in raw.columns:
        raw = raw.drop_duplicates("代码", keep="last")
    else:
        raw = raw.drop_duplicates("名称", keep="last")
    raw["主力净流入-净额"] = pd.to_numeric(raw.get("主力净流入-净额"), errors="coerce")
    return raw


def _fetch_eastmoney_rank_page_api(sector_type: str) -> pd.DataFrame:
    """Use the complete rank served by Eastmoney's public capital-flow page."""
    code = "m:90+s:4" if sector_type == "行业资金流" else "m:90+t:3"
    url = "https://data.eastmoney.com/dataapi/bkzj/getbkzj"
    # This host works directly on networks where push2 and the local proxy fail.
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(url, params={"key": "f62,f3,f184,f128", "code": code},
                               timeout=(5, 12), headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        payload = response.json()
    data = payload.get("data") or {}
    items = data.get("diff") or []
    total = pd.to_numeric(data.get("total"), errors="coerce")
    if payload.get("rc") != 0 or not isinstance(items, list) or not items or pd.isna(total):
        raise ValueError(f"东方财富网页接口没有返回有效{sector_type}排行")
    if len(items) != int(total):
        raise ValueError(f"东方财富网页接口{sector_type}仅返回 {len(items)} / {int(total)} 个板块")
    raw = pd.DataFrame(items)
    if not {"f12", "f14", "f62", "f3"}.issubset(raw.columns):
        raise ValueError(f"东方财富网页接口{sector_type}缺少必要字段")
    if raw["f12"].isna().any() or raw["f12"].duplicated().any():
        raise ValueError(f"东方财富网页接口{sector_type}存在无代码或重复板块")
    rank = _normalize_eastmoney_rank(raw)
    rank["主力净流入-净额"] = pd.to_numeric(rank["主力净流入-净额"], errors="coerce")
    return rank


def _fetch_eastmoney_rank(sector_type: str, fs: str) -> pd.DataFrame:
    """Fetch a complete industry or concept rank, preferring AKShare."""
    try:
        import akshare as ak

        rank = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type=sector_type)
        if rank is None or rank.empty:
            raise ValueError("AKShare 没有返回排行")
        rank = _normalize_eastmoney_rank(rank)
        rank["取数通道"] = "AKShare"
        return rank
    except Exception as ak_error:
        try:
            rank = _fetch_eastmoney_rank_page_api(sector_type)
            rank["取数通道"] = "东方财富官方网页接口（完整排行）"
            return rank
        except Exception as page_error:
            try:
                rank = _fetch_eastmoney_rank_direct(sector_type, fs)
                rank["取数通道"] = "东方财富备用接口（全分页）"
                return rank
            except Exception as fallback_error:
                raise ConnectionError(
                    f"东方财富排行各通道均失败（{sector_type}；AKShare: {str(ak_error)[:90]}；"
                    f"网页接口: {str(page_error)[:110]}；备用接口: {str(fallback_error)[:110]}）"
                ) from fallback_error


def _fetch_tonghuashun_rank_direct(sector_type: str) -> pd.DataFrame:
    """Read every full HTML page when AKShare's signed Ajax request fails."""
    board = "hyzjl" if sector_type == "行业资金流" else "gnzjl"
    # A name sort keeps boards on the same page while intraday prices change.
    base = f"https://data.10jqka.com.cn/funds/{board}/field/tradename/order/asc"
    headers = {
        "User-Agent": "Mozilla/5.0",
    }
    pages = []
    with requests.Session() as session:
        page_count = None
        page_number = 1
        while page_count is None or page_number <= page_count:
            url = f"{base}/" if page_number == 1 else f"{base}/page/{page_number}/"
            for attempt in range(3):
                try:
                    response = session.get(url, headers=headers, timeout=(5, 12))
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "lxml")
                    page_info = soup.select_one(".page_info")
                    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", page_info.get_text() if page_info else "")
                    table = soup.select_one("table.J-ajax-table")
                    if not match or table is None:
                        raise ValueError(f"同花顺{sector_type}第 {page_number} 页缺少有效分页或表格")
                    current_page, reported_count = map(int, match.groups())
                    if current_page != page_number or reported_count < 1 or (page_count is not None and reported_count != page_count):
                        raise ValueError(f"同花顺{sector_type}第 {page_number} 页分页信息不一致")
                    page = pd.read_html(StringIO(str(table)))[0]
                    if page.empty or (page_number < reported_count and len(page) < 50):
                        raise ValueError(f"同花顺{sector_type}第 {page_number} / {reported_count} 页数据不完整")
                    page_count = reported_count
                    break
                except (requests.RequestException, ValueError, IndexError) as exc:
                    if attempt == 2:
                        raise exc
            pages.append(page)
            page_number += 1
    rank = pd.concat(pages, ignore_index=True)
    required = {"序号", "行业", "涨跌幅", "净额(亿)", "领涨股"}
    missing = required.difference(rank.columns)
    if missing:
        raise ValueError(f"同花顺{sector_type}网页缺少字段：{'、'.join(sorted(missing))}")
    positions = pd.to_numeric(rank["序号"], errors="coerce")
    if positions.isna().any() or positions.astype(int).tolist() != list(range(1, len(rank) + 1)):
        raise ValueError(f"同花顺{sector_type}翻页期间出现缺行或重复行，拒绝保存")
    rank = rank.rename(columns={"涨跌幅": "行业-涨跌幅", "净额(亿)": "净额"})
    rank["行业-涨跌幅"] = pd.to_numeric(rank["行业-涨跌幅"].astype(str).str.rstrip("%"), errors="coerce")
    return rank


def _fetch_tonghuashun_rank(sector_type: str) -> pd.DataFrame:
    """Read the complete public Tonghuashun rank; its net amounts are in 亿元."""
    try:
        rank = _fetch_tonghuashun_rank_direct(sector_type)
        route = "同花顺公开网页（全分页）"
    except Exception as direct_error:
        try:
            import akshare as ak

            fetch = ak.stock_fund_flow_industry if sector_type == "行业资金流" else ak.stock_fund_flow_concept
            rank = fetch(symbol="即时")
            if rank is None or rank.empty:
                raise ValueError("AKShare 没有返回排行")
            route = "AKShare"
        except Exception as ak_error:
            raise ConnectionError(
                f"同花顺{sector_type}的公开网页和 AKShare 均失败（网页: {str(direct_error)[:120]}；"
                f"AKShare: {str(ak_error)[:100]}）"
            ) from ak_error
    required = {"行业", "行业-涨跌幅", "净额", "领涨股"}
    missing = required.difference(rank.columns)
    if missing:
        raise ValueError(f"同花顺{sector_type}缺少字段：{'、'.join(sorted(missing))}")
    rank = rank.rename(columns={
        "行业": "名称", "行业-涨跌幅": "今日涨跌幅", "领涨股": "今日主力净流入最大股",
    }).copy()
    net_yi = pd.to_numeric(rank["净额"], errors="coerce")
    if net_yi.notna().sum() == 0:
        raise ValueError(f"同花顺{sector_type}的资金净额均无效")
    rank["主力净流入-净额"] = net_yi * 1e8
    rank["主力净流入-净占比"] = pd.NA
    rank["代码"] = ""
    rank["取数通道"] = route
    return rank


def _fetch_provider_ranks(provider: str) -> tuple[list[pd.DataFrame], list[tuple[str, str]]]:
    ranks = []
    errors = []
    for sector_type, fs in _BOARD_QUERY_TYPES:
        try:
            rank = (_fetch_eastmoney_rank(sector_type, fs) if provider == "东方财富"
                    else _fetch_tonghuashun_rank(sector_type))
            required = {"名称", "主力净流入-净额", "今日涨跌幅"}
            missing = required.difference(rank.columns)
            if missing:
                raise ValueError(f"数据源字段变化，缺少：{'、'.join(sorted(missing))}")
            rank = rank.copy()
            rank["来源类型"] = sector_type
            rank["数据提供方"] = provider
            ranks.append(rank)
        except Exception as exc:
            errors.append((sector_type, f"{provider}: {str(exc)[:160]}"))
    return ranks, errors


def fetch_capital_flow_snapshot_with_diagnostics(
    as_of: datetime | None = None, preferred_provider: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch selected boards and report matched, missing, invalid and unknown labels.

    The provider reports a rolling daily aggregate, not tick-by-tick flow.
    Repeated snapshots are useful for showing how its reported aggregate changes
    during the session, but should not be interpreted as transaction-level data.
    """
    if preferred_provider not in (None, "东方财富", "同花顺"):
        raise ValueError(f"不支持的资金源：{preferred_provider}")
    if preferred_provider:
        ranks, fetch_errors = _fetch_provider_ranks(preferred_provider)
    else:
        eastmoney_ranks, eastmoney_errors = _fetch_provider_ranks("东方财富")
        if len(eastmoney_ranks) == len(_BOARD_QUERY_TYPES):
            ranks, fetch_errors = eastmoney_ranks, eastmoney_errors
        else:
            tonghuashun_ranks, tonghuashun_errors = _fetch_provider_ranks("同花顺")
            if tonghuashun_ranks:
                ranks, fetch_errors = tonghuashun_ranks, tonghuashun_errors
            else:
                ranks = eastmoney_ranks
                fetch_errors = eastmoney_errors + tonghuashun_errors
    if not ranks:
        raise ConnectionError("行业和概念资金排行都获取失败：" + "；".join(f"{kind}: {message}" for kind, message in fetch_errors))

    raw = pd.concat(ranks, ignore_index=True)
    raw["名称"] = raw["名称"].fillna("").astype(str).str.strip()
    raw["行业"] = raw["名称"].map(canonical_capital_flow_sector)
    tracked = raw.loc[raw["行业"].notna()].copy()
    if not tracked.empty:
        tracked["净流入额"] = pd.to_numeric(tracked["主力净流入-净额"], errors="coerce")
        tracked["板块顺序"] = tracked["行业"].map({name: i for i, name in enumerate(CAPITAL_FLOW_SECTORS)})
        tracked["别名优先级"] = tracked.apply(
            lambda row: next((i for i, alias in enumerate(_SECTOR_ALIASES[row["行业"]])
                              if _normalized_label(alias) == _normalized_label(row["名称"])), len(_SECTOR_ALIASES[row["行业"]])), axis=1
        )
        tracked["数值无效"] = tracked["净流入额"].isna()
        tracked = tracked.sort_values(["板块顺序", "数值无效", "别名优先级"]).drop_duplicates("行业", keep="first")

    stamp = pd.Timestamp(as_of or datetime.now().astimezone()).floor("min")
    if tracked.empty:
        data = pd.DataFrame(columns=["时间", "行业", "净流入额", "涨跌幅", "成交额", "主力净流入占比", "领涨股", "样本数", "数据来源"])
    else:
        tracked["涨跌幅"] = pd.to_numeric(tracked.get("今日涨跌幅"), errors="coerce")
        tracked["成交额"] = pd.to_numeric(tracked.get("今日成交额"), errors="coerce")
        tracked["主力净流入占比"] = pd.to_numeric(tracked.get("主力净流入-净占比"), errors="coerce")
        tracked["领涨股"] = tracked.get("今日主力净流入最大股", pd.Series("", index=tracked.index)).fillna("").astype(str).str.strip()
        data = pd.DataFrame({
            "时间": stamp.strftime("%Y-%m-%d %H:%M"),
            "行业": tracked["行业"].astype(str),
            "净流入额": tracked["净流入额"],
            "涨跌幅": tracked["涨跌幅"],
            "成交额": tracked["成交额"],
            "主力净流入占比": tracked["主力净流入占比"],
            "领涨股": tracked["领涨股"],
            "样本数": pd.NA,
            "数据来源": tracked.apply(lambda row: f"{row['数据提供方']}{row['来源类型']}（{row.get('取数通道', '未知通道')}）", axis=1),
        })
        data = data.loc[data["净流入额"].notna()].copy()
        data["板块顺序"] = data["行业"].map({name: i for i, name in enumerate(CAPITAL_FLOW_SECTORS)})
        data = data.sort_values("板块顺序").drop(columns="板块顺序").reset_index(drop=True)

    diagnostics = []
    for sector in CAPITAL_FLOW_SECTORS:
        matched = raw.loc[raw["行业"].eq(sector)]
        valid = data.loc[data["行业"].eq(sector)]
        if not valid.empty:
            match = tracked.loc[tracked["行业"].eq(sector)].iloc[0]
            status = "已采集"
            source_label = match["名称"]
            source_code = str(match.get("代码", ""))
            route = str(match.get("取数通道", "未知通道"))
            detail = ""
        elif not matched.empty:
            status = "数值无效"
            source_label = ", ".join(matched["名称"].astype(str).tolist())
            source_code = ", ".join(matched.get("代码", pd.Series(dtype=str)).fillna("").astype(str).tolist())
            route = ", ".join(matched.get("取数通道", pd.Series(dtype=str)).fillna("").astype(str).unique().tolist())
            detail = "源端返回了板块名称，但主力净流入数值为空或无法解析。"
        else:
            expected_types = _SECTOR_SOURCE_TYPES.get(sector, ("行业资金流",))
            failed = [(kind, message) for kind, message in fetch_errors if kind in expected_types]
            if len(failed) == len(expected_types):
                status = "来源获取失败"
            elif failed:
                status = "部分来源获取失败"
            else:
                status = "源端未返回"
            source_label = ""
            source_code = ""
            routes = raw.loc[raw["来源类型"].isin(expected_types), "取数通道"].dropna().astype(str).unique().tolist()
            route = " / ".join(routes)
            detail = "；".join(f"{kind}: {message}" for kind, message in failed) if failed else "在对应来源排行中没有同名板块；未用近似板块代填。"
        diagnostics.append({"行业": sector, "预期来源": " / ".join(_SECTOR_SOURCE_TYPES.get(sector, ("行业资金流",))),
                            "取数通道": route, "状态": status, "源标签": source_label, "源代码": source_code, "说明": detail})

    for _, row in raw.loc[raw["行业"].isna()].iterrows():
        diagnostics.append({"行业": "（未匹配）", "预期来源": row["来源类型"], "状态": "源名称未识别",
                            "取数通道": row.get("取数通道", "未知通道"), "源标签": row["名称"],
                            "源代码": str(row.get("代码", "")), "说明": "未自动归入任一关注板块。"})
    return {"snapshot": data.reset_index(drop=True), "diagnostics": pd.DataFrame(diagnostics)}


def fetch_industry_capital_flow(as_of: datetime | None = None) -> pd.DataFrame:
    """Backward-compatible snapshot-only interface."""
    return fetch_capital_flow_snapshot_with_diagnostics(as_of)["snapshot"]
