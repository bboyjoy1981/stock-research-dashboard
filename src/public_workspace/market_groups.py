"""Original pure categorical-market coverage and sample rules."""
import pandas as pd


def market_group_display_mask(df: pd.DataFrame, field: str, include_unclassified: bool = False) -> pd.Series:
    """Return rows safe to show in a categorical market map.

    An incomplete export should not create one dominant anonymous tile. The
    caller can still opt into seeing every record for audit purposes.
    """
    if field not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    labels = df[field].fillna("").astype(str).str.strip()
    if include_unclassified:
        return pd.Series(True, index=df.index, dtype=bool)
    return labels.ne("") & ~labels.isin({"未分类", "未细分", "nan", "None", "--", "—"})


def researchable_market_groups(grouped: pd.DataFrame, minimum_samples: int = 3) -> pd.DataFrame:
    """Keep tiny groups out of research rankings without altering map data."""
    if "股票数" not in grouped.columns:
        return grouped.copy()
    threshold = max(1, int(minimum_samples))
    counts = pd.to_numeric(grouped["股票数"], errors="coerce").fillna(0)
    return grouped.loc[counts >= threshold].copy()

