"""Safe market-data adapters.

The app never stores provider credentials.  Manual exports remain the default;
Tushare is optional and only enabled when TUSHARE_TOKEN is present.
"""
import os
from datetime import date, timedelta
import pandas as pd


def available_sources() -> list[str]:
    sources = ["演示数据", "同花顺导入文件"]
    if os.getenv("TUSHARE_TOKEN"):
        sources.append("Tushare Pro（日线）")
    return sources


def tushare_configured() -> bool:
    return bool(os.getenv("TUSHARE_TOKEN"))


def fetch_tushare_daily(ts_code: str, start_date: str | None = None,
                        end_date: str | None = None) -> pd.DataFrame:
    """Fetch daily OHLCV through Tushare Pro; raises a useful error if absent."""
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("未配置 TUSHARE_TOKEN；请先使用导入文件或演示数据")
    try:
        import tushare as ts
    except ImportError as exc:
        raise RuntimeError("当前环境未安装 tushare，请安装后重启应用") from exc
    end = end_date or date.today().strftime("%Y%m%d")
    start = start_date or (date.today() - timedelta(days=365)).strftime("%Y%m%d")
    pro = ts.pro_api(token)
    return pro.daily(ts_code=ts_code, start_date=start, end_date=end)


def source_status() -> dict[str, str]:
    return {
        "Tushare Pro": "已配置" if tushare_configured() else "未配置",
        "说明": "实时/分钟行情仍应使用有授权的终端或行情服务",
    }
