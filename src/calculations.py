REGIMES = {
    "系统风险": (0.20, 0.30, 0.10), "弱势震荡": (0.40, 0.50, 0.30),
    "修复阶段": (0.60, 0.70, 0.50), "主升阶段": (0.80, 0.95, 0.65),
    "高位震荡": (0.55, 0.70, 0.45),
}


def stock_snapshot_history(history, code, through_date=None):
    """Return observed daily snapshots for one stock, without inventing missing data."""
    import pandas as pd

    fields = ["交易日", "价格", "涨跌幅", "成交额"]
    if history is None or not isinstance(history, pd.DataFrame) or not {"快照日期", "代码"}.issubset(history.columns):
        return pd.DataFrame(columns=fields)
    normalized_codes = history["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    selected_code = str(code).removesuffix(".0").zfill(6)
    dates = history["快照日期"].fillna("").astype(str).str.strip()
    mask = normalized_codes.eq(selected_code) & dates.ne("")
    if through_date:
        mask &= dates.le(str(through_date))
    selected = history.loc[mask].copy()
    if selected.empty:
        return pd.DataFrame(columns=fields)
    selected["交易日"] = dates.loc[mask]
    selected = selected.drop_duplicates("交易日", keep="last").sort_values("交易日")
    for field in fields[1:]:
        selected[field] = pd.to_numeric(selected[field], errors="coerce") if field in selected else float("nan")
    return selected[fields].reset_index(drop=True)


def market_sector_turnover(stocks, group_field):
    """Aggregate reported turnover by group, never substituting market cap."""
    import pandas as pd

    if stocks is None or not isinstance(stocks, pd.DataFrame) or group_field not in stocks.columns:
        return pd.DataFrame(columns=[group_field, "成交额"])
    frame = stocks[[group_field]].copy()
    frame["成交额"] = pd.to_numeric(stocks["成交额"], errors="coerce") if "成交额" in stocks else float("nan")
    return frame.groupby(group_field, dropna=False, as_index=False).agg(成交额=("成交额", lambda values: values.sum(min_count=1)))


def research_context_label(context):
    """Return a compact breadcrumb for a cross-page market research path."""
    if not isinstance(context, dict):
        return None
    source = str(context.get("source") or "").strip()
    industry = str(context.get("industry") or "").strip()
    parts = [part for part in (source, industry) if part]
    return f"当前研究路径：{' → '.join(parts)}" if parts else None


def filter_stocks_by_research_context(frame, context, group_fields):
    """Return stocks matching the selected market-research industry context."""
    import pandas as pd

    if frame is None or frame.empty or not isinstance(context, dict):
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    industry = str(context.get("industry") or "").strip()
    available_fields = [field for field in group_fields if field in frame.columns]
    if not industry or not available_fields:
        return frame.copy()
    mask = pd.Series(False, index=frame.index)
    for field in available_fields:
        values = frame[field].fillna("").astype(str)
        mask |= values.str.contains(industry, case=False, regex=False)
    return frame.loc[mask].copy()


def calculate_market_score(values):
    return sum(int(v) for v in values)


def market_breadth_metrics(frame):
    """Summarize only valid imported quote rows; absent fields remain unknown."""
    if frame is None or "涨跌幅" not in frame.columns:
        return None
    import pandas as pd
    changes = pd.to_numeric(frame["涨跌幅"], errors="coerce").dropna()
    if changes.empty:
        return None
    result = {
        "valid": int(changes.size), "total": int(len(frame)),
        "up": int((changes > 0).sum()), "down": int((changes < 0).sum()),
        "flat": int((changes == 0).sum()), "median_pct": float(changes.median()),
    }
    result["advance_ratio"] = result["up"] / result["valid"]
    result["breadth_read"] = (
        "broad_advance" if result["advance_ratio"] >= 0.60 and result["median_pct"] > 0
        else "broad_decline" if result["advance_ratio"] <= 0.40 and result["median_pct"] < 0
        else "mixed"
    )
    if "成交额" in frame.columns:
        amounts = pd.to_numeric(frame["成交额"], errors="coerce").dropna()
        result["amount_sum"] = float(amounts.sum()) if not amounts.empty else None
        result["amount_rows"] = int(amounts.size)
    return result


def market_regime(score):
    name = "系统风险" if score <= 1 else "弱势震荡" if score == 2 else "修复阶段" if score <= 4 else "主升阶段"
    low, high, attack = REGIMES[name]
    return {"name": name, "total_low": low, "total_high": high, "attack_max": attack, "cash": 1 - high}


def compare_market_snapshots(current, previous, total_assets):
    """Return interpretable deltas between saved regime snapshots."""
    score = int(current.get("score", 0))
    regime = market_regime(score)
    result = {
        "previous": previous,
        "current_stage": current.get("stage", regime["name"]),
        "previous_stage": previous.get("stage") if previous else None,
        "stage_changed": bool(previous and previous.get("stage") != current.get("stage", regime["name"])),
        "score_delta": score - int(previous.get("score", score)) if previous else None,
        "position_low": float(total_assets) * regime["total_low"],
        "position_high": float(total_assets) * regime["total_high"],
    }
    if previous:
        prior = market_regime(int(previous.get("score", score)))
        result["position_low_delta"] = float(total_assets) * (regime["total_low"] - prior["total_low"])
        result["position_high_delta"] = float(total_assets) * (regime["total_high"] - prior["total_high"])
        old_breadth = previous.get("breadth", {}).get("advance_ratio")
        new_breadth = current.get("breadth", {}).get("advance_ratio")
        result["advance_ratio_delta"] = float(new_breadth) - float(old_breadth) if old_breadth is not None and new_breadth is not None else None
    else:
        result.update({"position_low_delta": None, "position_high_delta": None, "advance_ratio_delta": None})
    return result


def position_targets(total_assets, regime):
    low, high, attack = REGIMES[regime]
    return {"total_low": total_assets * low, "total_high": total_assets * high, "attack_max": total_assets * attack, "cash_min": total_assets * (1 - high)}


def calculate_position_status(actual_value, total_assets, low, high):
    ratio = actual_value / total_assets if total_assets else 0
    return "超配" if ratio > high else "低配" if ratio < low else "正常"


def portfolio_risk_summary(positions, total_assets):
    market_value = sum(max(0.0, float(row.get("amount") or 0.0)) for row in positions)
    risk_rows = [
        max(0.0, float(row.get("amount") or 0.0)) * float(row["stop_pct"])
        for row in positions
        if float(row.get("amount") or 0.0) > 0
        and row.get("stop_pct") is not None
        and 0 <= float(row["stop_pct"]) <= 1
    ]
    held_count = sum(float(row.get("amount") or 0.0) > 0 for row in positions)
    return {
        "market_value": market_value,
        "portfolio_ratio": market_value / total_assets if total_assets else 0.0,
        "estimated_loss": sum(risk_rows),
        "risk_ratio": sum(risk_rows) / total_assets if total_assets else 0.0,
        "unprotected_positions": max(0, held_count - len(risk_rows)),
    }


def compare_stock_pool(frame, codes, limit=6):
    """Return selected stock rows in the user's requested order, capped for comparison."""
    import pandas as pd
    if frame is None or getattr(frame, "empty", True) or "代码" not in frame.columns:
        return pd.DataFrame()
    wanted = [str(code).strip() for code in codes if str(code).strip()][:limit]
    if not wanted:
        return frame.iloc[0:0].copy()
    normalized = frame.copy()
    normalized["代码"] = normalized["代码"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    rows = []
    for code in wanted:
        match = normalized[normalized["代码"] == code]
        if not match.empty:
            rows.append(match.iloc[0])
    return pd.DataFrame(rows).reset_index(drop=True) if rows else frame.iloc[0:0].copy()


def market_close_summary(frame):
    """Build a compact close summary for the decision cockpit."""
    breadth = market_breadth_metrics(frame)
    if not breadth:
        return {"status": "no_quote", "message": "暂无可用涨跌幅数据"}
    status = "偏强" if breadth["breadth_read"] == "broad_advance" else "偏弱" if breadth["breadth_read"] == "broad_decline" else "分化"
    return {
        "status": status,
        "valid": breadth["valid"],
        "up": breadth["up"],
        "down": breadth["down"],
        "advance_ratio": breadth["advance_ratio"],
        "median_pct": breadth["median_pct"],
        "amount_sum": breadth.get("amount_sum"),
        "amount_rows": breadth.get("amount_rows", 0),
    }


def market_component_extremes(frame, size_field="成交额"):
    """Return compact, data-derived leader/laggard/activity rows for a group."""
    import pandas as pd
    if frame is None or getattr(frame, "empty", True) or "涨跌幅" not in frame.columns:
        return {}
    working = frame.copy()
    working["涨跌幅"] = pd.to_numeric(working["涨跌幅"], errors="coerce")
    working = working.dropna(subset=["涨跌幅"])
    if working.empty:
        return {}
    if size_field not in working.columns:
        working[size_field] = 0.0
    working[size_field] = pd.to_numeric(working[size_field], errors="coerce").fillna(0.0)

    def compact(row):
        return {
            "代码": str(row.get("代码", "")),
            "名称": str(row.get("名称", "未命名")),
            "涨跌幅": float(row["涨跌幅"]),
            "规模": float(row[size_field]),
        }

    return {
        "leader": compact(working.sort_values("涨跌幅", ascending=False).iloc[0]),
        "laggard": compact(working.sort_values("涨跌幅", ascending=True).iloc[0]),
        "active": compact(working.sort_values(size_field, ascending=False).iloc[0]),
    }


def market_map_leaves(stocks, grouped, hierarchy, size_field, color_field, parent_field=None):
    """Build stock-level treemap leaves while retaining the selected group metric."""
    import pandas as pd
    output_columns = ([parent_field] if parent_field else []) + [hierarchy, "个股", "云图标签", "面积", "云图颜色", "涨跌幅"]
    required = {hierarchy, "涨跌幅"}
    if stocks is None or getattr(stocks, "empty", True) or not required.issubset(stocks.columns):
        return pd.DataFrame(columns=output_columns)
    leaves = stocks.copy()
    leaves[hierarchy] = leaves[hierarchy].fillna("未分类").astype(str)
    leaves["涨跌幅"] = pd.to_numeric(leaves["涨跌幅"], errors="coerce")
    leaves = leaves.dropna(subset=["涨跌幅"])
    if leaves.empty:
        return pd.DataFrame(columns=output_columns)
    if parent_field and parent_field in leaves.columns:
        leaves[parent_field] = leaves[parent_field].fillna("未分类").astype(str).replace("", "未分类")
    if size_field == "等权":
        leaves["面积"] = 1.0
    else:
        sizes = pd.to_numeric(leaves.get(size_field, pd.Series(float('nan'), index=leaves.index)), errors="coerce")
        leaves["面积"] = sizes
        leaves = leaves.loc[sizes.gt(0)].copy()
        if leaves.empty:
            return pd.DataFrame(columns=output_columns)
    codes = leaves.get("代码", pd.Series("", index=leaves.index)).fillna("").astype(str)
    names = leaves.get("名称", pd.Series("未命名", index=leaves.index)).fillna("未命名").astype(str)
    leaves["个股"] = codes.where(codes.ne(""), "个股") + " · " + names
    leaves["云图标签"] = names + "\n" + leaves["涨跌幅"].map(lambda value: f"{value:+.2f}%")
    if color_field == "涨跌幅":
        leaves["云图颜色"] = leaves["涨跌幅"]
    else:
        leaves["云图颜色"] = float("nan")
        if grouped is not None and hierarchy in grouped.columns and color_field in grouped.columns:
            if parent_field and parent_field in grouped.columns and parent_field in leaves.columns:
                group_keys = [parent_field, hierarchy]
                lookup = grouped.drop_duplicates(group_keys).set_index(group_keys)[color_field]
                leaf_keys = pd.MultiIndex.from_frame(leaves[group_keys])
                leaves["云图颜色"] = lookup.reindex(leaf_keys).to_numpy()
            else:
                lookup = grouped.drop_duplicates(hierarchy).set_index(hierarchy)[color_field]
                leaves["云图颜色"] = leaves[hierarchy].map(lookup)
    available_columns = [field for field in output_columns if field in leaves.columns]
    return leaves[available_columns].reset_index(drop=True)


def market_map_area_options(stocks):
    """Offer only real positive size fields, or an explicitly equal-area map."""
    import pandas as pd

    if stocks is None or not isinstance(stocks, pd.DataFrame):
        return ["等权"]
    options = [
        field for field in ("成交额", "流通市值", "总市值")
        if field in stocks.columns and pd.to_numeric(stocks[field], errors="coerce").gt(0).any()
    ]
    return options or ["等权"]


def limit_market_map_leaves(leaves, hierarchy, maximum_per_group=None, parent_field=None):
    """Keep a readable number of the highest-activity stock tiles per group."""
    import pandas as pd
    if leaves is None or getattr(leaves, "empty", True) or not maximum_per_group:
        return leaves.copy() if hasattr(leaves, "copy") else pd.DataFrame()
    if hierarchy not in leaves.columns or "面积" not in leaves.columns:
        return leaves.copy()
    maximum = max(1, int(maximum_per_group))
    groups = [parent_field, hierarchy] if parent_field and parent_field in leaves.columns else [hierarchy]
    ranked = leaves.sort_values([*groups, "面积"], ascending=[*[True] * len(groups), False])
    return ranked.groupby(groups, group_keys=False).head(maximum).reset_index(drop=True)


def sector_rotation_board(frame, group_field):
    """Score industry snapshots by relative strength, breadth and activity.

    The result is deliberately a descriptive end-of-day sorting aid.  It does
    not infer a future move or generate a trading instruction.
    """
    import pandas as pd

    required = {group_field, "涨跌幅", "上涨占比", "成交额"}
    if frame is None or getattr(frame, "empty", True) or not required.issubset(frame.columns):
        return pd.DataFrame(columns=[group_field, "涨跌幅", "上涨占比", "成交额", "轮动热度", "轮动状态"])
    board = frame.copy()
    for field in ("涨跌幅", "上涨占比", "成交额"):
        board[field] = pd.to_numeric(board[field], errors="coerce").fillna(0.0)
    board[group_field] = board[group_field].fillna("未分类").astype(str)

    def scaled(values):
        lower, upper = values.min(), values.max()
        if pd.isna(lower) or pd.isna(upper) or upper == lower:
            return pd.Series(0.5, index=values.index)
        return (values - lower) / (upper - lower)

    board["轮动热度"] = (
        scaled(board["涨跌幅"]) * 45
        + scaled(board["上涨占比"]) * 35
        + scaled(board["成交额"]) * 20
    ).round().astype(int)
    board["轮动状态"] = "分化观察"
    board.loc[(board["涨跌幅"] > 0) & (board["上涨占比"] >= 0.55), "轮动状态"] = "强势扩散"
    board.loc[(board["涨跌幅"] < 0) & (board["上涨占比"] < 0.45), "轮动状态"] = "承压"
    board.loc[(board["涨跌幅"] > 0) & (board["上涨占比"] < 0.55), "轮动状态"] = "个股驱动"
    return board.sort_values(["轮动热度", "涨跌幅", "成交额"], ascending=[False, False, False]).reset_index(drop=True)


def stock_top_percent(value, sample):
    """Competition rank from the top; equal observations share the same rank."""
    import pandas as pd
    current = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    values = pd.to_numeric(pd.Series(sample), errors="coerce").dropna()
    if pd.isna(current) or values.empty:
        return None
    return min(100.0, (int(values.gt(current).sum()) + 1) / len(values) * 100)


def stock_relative_snapshot(stock_change, market_changes, peer_changes=None):
    """Describe a stock's current snapshot relative to market and peers."""
    import pandas as pd

    stock_value = pd.to_numeric(pd.Series([stock_change]), errors="coerce").iloc[0]
    market = pd.to_numeric(pd.Series(market_changes), errors="coerce").dropna()
    peers = pd.to_numeric(pd.Series(peer_changes if peer_changes is not None else []), errors="coerce").dropna()
    result = {
        "个股涨跌": float(stock_value) if pd.notna(stock_value) else None,
        "市场平均": float(market.mean()) if not market.empty else None,
        "同类平均": float(peers.mean()) if not peers.empty else None,
        "相对市场": None,
        "相对同类": None,
        "同类位置": None,
    }
    if result["个股涨跌"] is not None and result["市场平均"] is not None:
        result["相对市场"] = result["个股涨跌"] - result["市场平均"]
    if result["个股涨跌"] is not None and result["同类平均"] is not None:
        result["相对同类"] = result["个股涨跌"] - result["同类平均"]
        combined = pd.concat([peers, pd.Series([result["个股涨跌"]])], ignore_index=True)
        result["同类位置"] = float(combined.rank(pct=True).iloc[-1] * 100)
    return result


def index_pulse_snapshot(frame):
    """Create an end-of-day breadth summary from an imported index snapshot."""
    import pandas as pd

    if frame is None or getattr(frame, "empty", True) or not {"名称", "涨跌幅"}.issubset(frame.columns):
        return None
    indices = frame[["名称", "涨跌幅"]].copy()
    indices["涨跌幅"] = pd.to_numeric(indices["涨跌幅"], errors="coerce")
    indices = indices.dropna(subset=["涨跌幅"])
    if indices.empty:
        return None
    strongest = indices.sort_values("涨跌幅", ascending=False).iloc[0]
    weakest = indices.sort_values("涨跌幅", ascending=True).iloc[0]
    return {
        "样本数量": int(len(indices)),
        "上涨数量": int((indices["涨跌幅"] > 0).sum()),
        "下跌数量": int((indices["涨跌幅"] < 0).sum()),
        "平均涨跌": float(indices["涨跌幅"].mean()),
        "离散度": float(indices["涨跌幅"].max() - indices["涨跌幅"].min()),
        "最强名称": str(strongest["名称"]),
        "最弱名称": str(weakest["名称"]),
    }


def market_sector_tiers(frame, group_field):
    """Classify a sector ranking snapshot into readable strength tiers."""
    import pandas as pd

    if frame is None or getattr(frame, "empty", True) or not {group_field, "涨跌幅"}.issubset(frame.columns):
        return pd.DataFrame(columns=[group_field, "涨跌幅", "强弱梯队"])
    tiers = frame.copy()
    tiers["涨跌幅"] = pd.to_numeric(tiers["涨跌幅"], errors="coerce")
    tiers = tiers.dropna(subset=["涨跌幅"])
    if tiers.empty:
        return tiers.assign(强弱梯队=pd.Series(dtype="string"))
    tiers["强弱梯队"] = "震荡观察"
    tiers.loc[tiers["涨跌幅"] >= 2, "强弱梯队"] = "强势领涨"
    tiers.loc[(tiers["涨跌幅"] >= 0.5) & (tiers["涨跌幅"] < 2), "强弱梯队"] = "偏强跟随"
    tiers.loc[tiers["涨跌幅"] <= -1, "强弱梯队"] = "弱势承压"
    return tiers.sort_values("涨跌幅", ascending=False).reset_index(drop=True)


def industry_chain_summary(frame, groups, text_columns):
    """Aggregate a keyword-defined industry chain from an imported snapshot."""
    import pandas as pd

    if frame is None or getattr(frame, "empty", True):
        return pd.DataFrame(columns=["产业链", "股票数", "平均涨跌", "上涨占比", "成交额"])
    usable_columns = [field for field in text_columns if field in frame.columns]
    if not usable_columns:
        return pd.DataFrame(columns=["产业链", "股票数", "平均涨跌", "上涨占比", "成交额"])
    working = frame.copy()
    changes = pd.to_numeric(working.get("涨跌幅", pd.Series(index=working.index, dtype=float)), errors="coerce")
    amounts = pd.to_numeric(working.get("成交额", pd.Series(index=working.index, dtype=float)), errors="coerce").fillna(0.0)
    rows = []
    for title, terms in groups.items():
        matched = pd.Series(False, index=working.index)
        for field in usable_columns:
            values = working[field].fillna("").astype(str)
            for term in terms:
                matched |= values.str.contains(str(term), case=False, regex=False)
        selected_changes = changes.loc[matched].dropna()
        rows.append({
            "产业链": str(title),
            "股票数": int(matched.sum()),
            "平均涨跌": float(selected_changes.mean()) if not selected_changes.empty else None,
            "上涨占比": float((selected_changes > 0).mean()) if not selected_changes.empty else None,
            "成交额": float(amounts.loc[matched].sum()),
        })
    return pd.DataFrame(rows)


def market_close_review(stocks, sectors, sector_field):
    """Return a concise, descriptive close-review snapshot for the market home."""
    import pandas as pd

    changes = pd.to_numeric(stocks.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna() if stocks is not None else pd.Series(dtype=float)
    up, down = int((changes > 0).sum()), int((changes < 0).sum())
    state = "普涨" if up > down * 1.5 else "普跌" if down > up * 1.5 else "结构分化"
    result = {
        "市场状态": state,
        "上涨家数": up,
        "下跌家数": down,
        "平盘家数": int((changes == 0).sum()),
        "平均涨跌": float(changes.mean()) if not changes.empty else None,
        "涨停附近": int((changes >= 9.8).sum()),
        "跌停附近": int((changes <= -9.8).sum()),
        "领涨行业": None,
        "领跌行业": None,
    }
    if sectors is not None and not getattr(sectors, "empty", True) and {sector_field, "涨跌幅"}.issubset(sectors.columns):
        grouped = sectors[[sector_field, "涨跌幅"]].copy()
        grouped["涨跌幅"] = pd.to_numeric(grouped["涨跌幅"], errors="coerce")
        grouped = grouped.dropna(subset=["涨跌幅"])
        if not grouped.empty:
            result["领涨行业"] = str(grouped.sort_values("涨跌幅", ascending=False).iloc[0][sector_field])
            result["领跌行业"] = str(grouped.sort_values("涨跌幅", ascending=True).iloc[0][sector_field])
    return result


def market_overview_radar(stocks, sectors, sector_field):
    """Build a compact end-of-day research radar from one market snapshot."""
    import pandas as pd

    changes = pd.to_numeric(
        stocks.get("涨跌幅", pd.Series(dtype=float)) if stocks is not None else pd.Series(dtype=float),
        errors="coerce",
    ).dropna()
    advance_ratio = float((changes > 0).mean()) if not changes.empty else None
    breadth_status = "数据不足"
    if advance_ratio is not None:
        breadth_status = "广度扩散" if advance_ratio >= 0.6 else "广度收缩" if advance_ratio <= 0.4 else "广度分化"
    result = {
        "上涨占比": advance_ratio,
        "广度状态": breadth_status,
        "领涨行业": None,
        "领跌行业": None,
        "活跃行业": None,
    }
    required = {sector_field, "涨跌幅"}
    if sectors is None or getattr(sectors, "empty", True) or not required.issubset(sectors.columns):
        return result
    frame = sectors.copy()
    frame["涨跌幅"] = pd.to_numeric(frame["涨跌幅"], errors="coerce")
    frame = frame.dropna(subset=[sector_field, "涨跌幅"])
    if frame.empty:
        return result
    result["领涨行业"] = str(frame.sort_values("涨跌幅", ascending=False).iloc[0][sector_field])
    result["领跌行业"] = str(frame.sort_values("涨跌幅", ascending=True).iloc[0][sector_field])
    if "成交额" in frame.columns:
        frame["成交额"] = pd.to_numeric(frame["成交额"], errors="coerce")
        if frame["成交额"].notna().any():
            result["活跃行业"] = str(frame.sort_values("成交额", ascending=False).iloc[0][sector_field])
    return result


def market_research_queue(frame, group_field):
    """Create three distinct, descriptive industry follow-up leads from a close snapshot."""
    import pandas as pd

    columns = [group_field, "涨跌幅", "上涨占比", "成交额", "行业强度"]
    if frame is None or getattr(frame, "empty", True) or not set(columns).issubset(frame.columns):
        return pd.DataFrame(columns=["研究角度", group_field, "涨跌幅", "上涨占比", "成交额", "行业强度", "相对市场"])
    working = frame[columns].copy()
    for field in ("涨跌幅", "上涨占比", "成交额", "行业强度"):
        working[field] = pd.to_numeric(working[field], errors="coerce")
    working = working.dropna(subset=[group_field, "涨跌幅"])
    if working.empty:
        return pd.DataFrame(columns=["研究角度", group_field, "涨跌幅", "上涨占比", "成交额", "行业强度", "相对市场"])
    working[group_field] = working[group_field].astype(str)
    working["成交额"] = working["成交额"].fillna(0.0)
    working["行业强度"] = working["行业强度"].fillna(0.0)
    working["上涨占比"] = working["上涨占比"].fillna(0.0)
    working["相对市场"] = (working["涨跌幅"] - working["涨跌幅"].mean()).round(2)

    candidates = [
        ("强度领先", working.sort_values(["行业强度", "成交额"], ascending=[False, False])),
        ("规模活跃", working.sort_values(["成交额", "行业强度"], ascending=[False, False])),
        ("相对市场偏离", working.assign(_偏离=working["相对市场"].abs()).sort_values(["_偏离", "相对市场"], ascending=[False, True])),
    ]
    rows = []
    for angle, ordered in candidates:
        if not ordered.empty:
            item = ordered.iloc[0].drop(labels=["_偏离"], errors="ignore").to_dict()
            item["研究角度"] = angle
            rows.append(item)
    return pd.DataFrame(rows)[["研究角度", group_field, "涨跌幅", "上涨占比", "成交额", "行业强度", "相对市场"]]


def market_activity_concentration(frame, size_field="成交额", top_n=10):
    """Summarize how concentrated a market snapshot's reported turnover is."""
    import pandas as pd

    empty = {"有效样本": 0, "总成交额": 0.0, "前N成交额": 0.0, "前N成交占比": None, "N": max(1, int(top_n))}
    if frame is None or getattr(frame, "empty", True) or size_field not in frame.columns:
        return empty
    values = pd.to_numeric(frame[size_field], errors="coerce").dropna().clip(lower=0.0)
    if values.empty:
        return empty
    limit = min(max(1, int(top_n)), len(values))
    total = float(values.sum())
    leading = float(values.nlargest(limit).sum())
    return {
        "有效样本": int(len(values)),
        "总成交额": total,
        "前N成交额": leading,
        "前N成交占比": leading / total if total > 0 else None,
        "N": limit,
    }


def market_snapshot_trend(history, through_date=None):
    """Aggregate locally saved end-of-day snapshots into a small market trend."""
    import pandas as pd

    columns = ["交易日", "上涨占比", "平均涨跌", "成交额", "成交额有效数", "样本数", "涨停附近", "跌停附近"]
    if history is None or getattr(history, "empty", True) or not {"快照日期", "涨跌幅"}.issubset(history.columns):
        return pd.DataFrame(columns=columns)
    frame = history.copy()
    frame["快照日期"] = frame["快照日期"].fillna("").astype(str).str.strip()
    if through_date:
        frame = frame.loc[frame["快照日期"].le(str(through_date))].copy()
    frame["涨跌幅"] = pd.to_numeric(frame["涨跌幅"], errors="coerce")
    frame = frame.loc[frame["快照日期"].ne("") & frame["涨跌幅"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    if "成交额" not in frame.columns:
        frame["成交额"] = float("nan")
    frame["成交额"] = pd.to_numeric(frame["成交额"], errors="coerce")
    result = frame.groupby("快照日期", as_index=False).agg(
        上涨占比=("涨跌幅", lambda values: float((values > 0).mean())),
        平均涨跌=("涨跌幅", "mean"),
        成交额=("成交额", lambda values: values.sum(min_count=1)),
        成交额有效数=("成交额", "count"),
        样本数=("涨跌幅", "size"),
        涨停附近=("涨跌幅", lambda values: int((values >= 9.8).sum())),
        跌停附近=("涨跌幅", lambda values: int((values <= -9.8).sum())),
    ).rename(columns={"快照日期": "交易日"})
    return result[columns].sort_values("交易日").reset_index(drop=True)


def market_change_distribution(frame):
    """Count valid stock returns in review-friendly A-share return bands."""
    import pandas as pd

    labels = ["<-7%", "-7%~-3%", "-3%~0%", "0%", "0%~3%", "3%~7%", ">7%"]
    empty = pd.DataFrame({"区间": labels, "数量": [0] * len(labels)})
    if frame is None or getattr(frame, "empty", True) or "涨跌幅" not in frame.columns:
        return empty
    changes = pd.to_numeric(frame["涨跌幅"], errors="coerce").dropna()
    if changes.empty:
        return empty
    counts = [
        int((changes < -7).sum()),
        int(((changes >= -7) & (changes < -3)).sum()),
        int(((changes >= -3) & (changes < 0)).sum()),
        int(changes.eq(0).sum()),
        int(((changes > 0) & (changes <= 3)).sum()),
        int(((changes > 3) & (changes <= 7)).sum()),
        int((changes > 7).sum()),
    ]
    return pd.DataFrame({"区间": labels, "数量": counts})


def market_overview_distribution(frame):
    """Count close-to-close changes in seven exclusive bands, including flat."""
    import pandas as pd

    labels = ["<-5%", "-5%~-2%", "-2%~0%", "0%", "0%~2%", "2%~5%", ">5%"]
    if frame is None or "涨跌幅" not in frame.columns:
        return pd.DataFrame({"区间": labels, "家数": [0] * len(labels)})
    changes = pd.to_numeric(frame["涨跌幅"], errors="coerce").dropna()
    counts = [
        int((changes < -5).sum()),
        int(((changes >= -5) & (changes < -2)).sum()),
        int(((changes >= -2) & (changes < 0)).sum()),
        int(changes.eq(0).sum()),
        int(((changes > 0) & (changes <= 2)).sum()),
        int(((changes > 2) & (changes <= 5)).sum()),
        int((changes > 5).sum()),
    ]
    return pd.DataFrame({"区间": labels, "家数": counts})


def market_close_temperature(snapshot):
    """Describe end-of-day market participation without implying a trade action."""
    snapshot = snapshot or {}
    breadth = float(snapshot.get("上涨占比", 0) or 0)
    limit_up = int(snapshot.get("涨停附近", 0) or 0)
    limit_down = int(snapshot.get("跌停附近", 0) or 0)
    if breadth >= 0.68 and limit_up > limit_down:
        return {"状态": "情绪活跃", "说明": "上涨广度较高，涨停附近数量占优；继续核对成交是否集中。", "颜色": "red"}
    if breadth <= 0.35 and limit_down > limit_up:
        return {"状态": "情绪低迷", "说明": "下跌广度与跌停附近数量偏高；优先观察风险是否继续扩散。", "颜色": "green"}
    if limit_up > limit_down * 2 and breadth >= 0.45:
        return {"状态": "局部活跃", "说明": "强势个股较多但市场广度未完全同步，关注结构分化。", "颜色": "orange"}
    return {"状态": "市场分化", "说明": "广度与极端波动没有形成单一方向，适合按行业结构复盘。", "颜色": "blue"}


def market_history_coverage(trend):
    """Describe the date range actually represented by saved market snapshots."""
    if trend is None or getattr(trend, "empty", True) or "交易日" not in trend.columns:
        return {"交易日数": 0, "起始日": None, "截至日": None}
    dates = trend["交易日"].dropna().astype(str).str.strip()
    dates = dates.loc[dates.ne("")].drop_duplicates().sort_values()
    if dates.empty:
        return {"交易日数": 0, "起始日": None, "截至日": None}
    return {"交易日数": int(len(dates)), "起始日": dates.iloc[0], "截至日": dates.iloc[-1]}


def market_trend_summary(trend):
    """Summarize a saved market-history series for end-of-day review."""
    import pandas as pd

    empty = {"最高广度": None, "最低广度": None, "平均成交额": None}
    if trend is None or getattr(trend, "empty", True):
        return empty
    breadth = pd.to_numeric(trend["上涨占比"], errors="coerce").dropna() if "上涨占比" in trend else pd.Series(dtype=float)
    turnover = pd.to_numeric(trend["成交额"], errors="coerce").dropna() if "成交额" in trend else pd.Series(dtype=float)
    return {
        "最高广度": float(breadth.max()) if not breadth.empty else None,
        "最低广度": float(breadth.min()) if not breadth.empty else None,
        "平均成交额": float(turnover.mean()) if not turnover.empty else None,
    }


def decision_alerts(actual_value, total_assets, targets, risk_summary=None, close_summary=None):
    """Return concise, non-trading alerts for the decision cockpit."""
    alerts = []
    if total_assets and actual_value > targets["total_high"]:
        alerts.append("总仓位高于当前阶段参考上限")
    if total_assets and actual_value < targets["total_low"]:
        alerts.append("总仓位低于当前阶段参考下限")
    if risk_summary and risk_summary.get("unprotected_positions", 0):
        alerts.append(f"有 {risk_summary['unprotected_positions']} 只持仓未填写单票止损线")
    if close_summary and close_summary.get("status") == "no_quote":
        alerts.append("当前没有可用全市场涨跌幅数据")
    return alerts
