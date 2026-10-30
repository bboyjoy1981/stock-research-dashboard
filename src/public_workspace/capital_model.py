"""Original pure capital replay normalization, metrics and source segmentation."""
import re
import pandas as pd


def capital_replay_template() -> pd.DataFrame:
    """Template for post-market industry capital-flow snapshots."""
    return pd.DataFrame(columns=["时间", "行业", "净流入额", "涨跌幅", "成交额", "领涨股", "样本数"])


def _capital_replay_number(value):
    match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*(亿|万|元)?\s*", str(value).replace(",", ""))
    if not match:
        return pd.NA
    return float(match.group(1)) * {"亿": 1e8, "万": 1e4, "元": 1, None: 1}[match.group(2)]


def normalize_capital_replay(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a post-market industry capital-flow snapshot."""
    out = df.copy()
    out.columns = [str(col).replace("\ufeff", "").strip() for col in out.columns]
    aliases = {
        "日期时间": "时间", "时点": "时间", "时间点": "时间",
        "板块": "行业", "行业名称": "行业", "所属行业": "行业",
        "资金净流入": "净流入额", "主力净流入": "净流入额", "净额": "净流入额",
        "涨幅": "涨跌幅", "涨跌幅%": "涨跌幅",
        "成交金额": "成交额", "总金额": "成交额",
        "净流入占比": "主力净流入占比",
    }
    out = out.rename(columns={column: aliases[column] for column in out.columns if column in aliases})
    for field in ("行业", "领涨股"):
        if field in out:
            out[field] = out[field].fillna("").astype(str).str.strip()
    for field in ("净流入额", "成交额", "样本数"):
        if field in out:
            out[field] = out[field].map(_capital_replay_number)
    for field in ("涨跌幅", "主力净流入占比"):
        if field in out:
            out[field] = pd.to_numeric(out[field].astype(str).str.replace("%", "", regex=False), errors="coerce")
    if "时间" in out:
        parsed_time = pd.to_datetime(out["时间"], errors="coerce")
        out["时间"] = parsed_time.dt.strftime("%Y-%m-%d %H:%M").fillna(out["时间"].fillna("").astype(str).str.strip())
    return out


def capital_replay_industry_track(df: pd.DataFrame, industry: str) -> pd.DataFrame:
    """Return one industry's ordered net-flow snapshots for post-market replay."""
    replay = normalize_capital_replay(df)
    if not {"时间", "行业", "净流入额"}.issubset(replay.columns):
        return capital_replay_template().iloc[0:0]
    track = replay.loc[replay["行业"].astype(str).eq(str(industry)), ["时间", "净流入额"]].copy()
    track["净流入额"] = pd.to_numeric(track["净流入额"], errors="coerce")
    return track.dropna(subset=["时间", "净流入额"]).sort_values("时间").drop_duplicates("时间", keep="last").reset_index(drop=True)


def capital_replay_flow_changes(df: pd.DataFrame) -> pd.DataFrame:
    """Compare each industry's first and last recorded net-flow snapshots."""
    replay = normalize_capital_replay(df)
    required = {"时间", "行业", "净流入额"}
    if not required.issubset(replay.columns):
        return pd.DataFrame(columns=["行业", "首时点净流入", "末时点净流入", "净流入变化"])
    replay["净流入额"] = pd.to_numeric(replay["净流入额"], errors="coerce")
    replay = replay.dropna(subset=["时间", "行业", "净流入额"]).sort_values("时间")
    if replay.empty or replay["时间"].nunique() < 2:
        return pd.DataFrame(columns=["行业", "首时点净流入", "末时点净流入", "净流入变化"])
    first_time, last_time = replay["时间"].iloc[0], replay["时间"].iloc[-1]
    first = replay.loc[replay["时间"].eq(first_time), ["行业", "净流入额"]].drop_duplicates("行业", keep="last").rename(columns={"净流入额": "首时点净流入"})
    last = replay.loc[replay["时间"].eq(last_time), ["行业", "净流入额"]].drop_duplicates("行业", keep="last").rename(columns={"净流入额": "末时点净流入"})
    changes = first.merge(last, on="行业", how="inner")
    changes["净流入变化"] = changes["末时点净流入"] - changes["首时点净流入"]
    return changes.sort_values("净流入变化", ascending=False).reset_index(drop=True)


def capital_replay_readiness(df: pd.DataFrame) -> dict:
    """Describe whether a capital-flow upload can support intraday replay."""
    replay = normalize_capital_replay(df)
    required = {"时间", "行业", "净流入额"}
    if not required.issubset(replay.columns):
        return {"时点数": 0, "行业数": 0, "完整轨迹行业": 0, "完整轨迹占比": 0.0}
    replay = replay.dropna(subset=["时间", "行业", "净流入额"]).copy()
    replay["时间"] = replay["时间"].astype(str).str.strip()
    replay["行业"] = replay["行业"].astype(str).str.strip()
    replay = replay.loc[replay["时间"].ne("") & replay["行业"].ne("")].drop_duplicates(["时间", "行业"], keep="last")
    time_count = int(replay["时间"].nunique())
    industry_count = int(replay["行业"].nunique())
    complete = int((replay.groupby("行业")["时间"].nunique() == time_count).sum()) if time_count else 0
    return {
        "时点数": time_count,
        "行业数": industry_count,
        "完整轨迹行业": complete,
        "完整轨迹占比": complete / industry_count if industry_count else 0.0,
    }


def filter_capital_replay_by_date(df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    """Keep replay snapshots belonging to one YYYY-MM-DD trading day."""
    replay = normalize_capital_replay(df)
    if "时间" not in replay.columns:
        return replay.iloc[0:0].copy()
    target = str(trade_date).strip()
    return replay.loc[replay["时间"].astype(str).str.startswith(target)].sort_values("时间").reset_index(drop=True)


def capital_replay_snapshot_map(df: pd.DataFrame) -> pd.DataFrame:
    """Build safe treemap input for one industry capital-flow snapshot."""
    snapshot = normalize_capital_replay(df)
    if not {"行业", "净流入额"}.issubset(snapshot.columns):
        return pd.DataFrame(columns=["行业", "净流入额", "面积"])
    snapshot["净流入额"] = pd.to_numeric(snapshot["净流入额"], errors="coerce")
    if "成交额" in snapshot:
        turnover = pd.to_numeric(snapshot["成交额"], errors="coerce").fillna(0.0)
    else:
        turnover = pd.Series(0.0, index=snapshot.index)
    snapshot["面积"] = turnover.where(turnover.gt(0), snapshot["净流入额"].abs()).fillna(0.0)
    return snapshot.loc[snapshot["行业"].fillna("").astype(str).str.strip().ne("") & snapshot["净流入额"].notna(), :].copy()


def capital_replay_segments(day_replay):
    """Split one trading day whenever the published funding source changes."""
    if day_replay.empty or not {"时间", "数据来源"}.issubset(day_replay.columns):
        return [("未标明来源", day_replay)] if not day_replay.empty else []
    frame = day_replay.copy()
    frame["_资金源"] = frame["数据来源"].fillna("").astype(str).map(
        lambda value: next((name for name in ("东方财富", "同花顺") if value.startswith(name)), value.strip() or "未标明来源")
    )
    samples = frame[["时间", "_资金源"]].drop_duplicates().sort_values("时间", kind="stable").copy()
    samples["_片段"] = samples["_资金源"].ne(samples["_资金源"].shift()).cumsum()
    frame = frame.merge(samples, on=["时间", "_资金源"], how="left")
    segments = []
    for number, group in frame.groupby("_片段", sort=True):
        group = group.sort_values("时间").drop(columns=["_资金源", "_片段"])
        times = group["时间"].astype(str)
        label = f"{samples.loc[samples['_片段'].eq(number), '_资金源'].iloc[0]}｜{times.iloc[0][-5:]}起｜第{number}段"
        segments.append((label, group))
    return segments

def follow_latest_replay_date(state, key, dates):
    """Follow a newly published trading day once; preserve deliberate browsing."""
    if not dates:
        return None
    latest=dates[-1]
    seen=key+'_latest_seen'
    if state.get(seen)!=latest or state.get(key) not in dates:
        state[key]=latest
    state[seen]=latest
    return state[key]

