"""Portable, descriptive market review based only on the selected snapshot."""
import pandas as pd

from .calculations import market_close_review


def build_close_brief(stocks, *, date, origin, sectors=None, sector_field="行业"):
    frame = stocks.loc[:, ~stocks.columns.duplicated()].copy()
    changes = pd.to_numeric(frame.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
    amounts = pd.to_numeric(frame.get("成交额", pd.Series(dtype=float)), errors="coerce")
    amounts = amounts.loc[amounts.ge(0)].dropna()
    review = market_close_review(frame, sectors, sector_field)
    breadth = f"{(changes > 0).mean():.1%}" if not changes.empty else "未提供"
    mean = f"{changes.mean():+.2f}%" if not changes.empty else "未提供"
    amount = f"{amounts.sum() / 1e8:.2f} 亿元" if not amounts.empty else "未提供"
    return "\n".join([
        "市场收盘复盘简报", f"快照交易日：{date or '未提供'}", f"来源：{origin}",
        f"输入样本：{len(frame):,}", f"有效涨跌：{len(changes):,}/{len(frame):,}",
        f"市场状态：{review['市场状态'] if not changes.empty else '数据不足'}",
        f"上涨 / 下跌 / 平盘：{review['上涨家数']} / {review['下跌家数']} / {review['平盘家数']}",
        f"上涨占比：{breadth}（分母为有效涨跌样本）", f"平均涨跌：{mean}",
        f"已提供成交额合计：{amount}", f"成交额覆盖：{len(amounts):,}/{len(frame):,}",
        f"领涨分类：{review['领涨行业'] or '未提供'}", f"领跌分类：{review['领跌行业'] or '未提供'}",
        f"涨停附近 / 跌停附近：{review['涨停附近']} / {review['跌停附近']}",
        "口径：涨跌幅均值为样本等权；成交额仅汇总已提供的非负数值，不代表资金净流入。",
        "±9.8%仅为极端波动观察门槛，不等于确认涨跌停；不同交易板块限制不同。",
        "分类排行取当前页面的有效分类及样本门槛，不代表完整行业成分。",
        "次日研究顺序：核对快照日期与覆盖 → 云图检查行业结构 → 个股卡核对量价与历史。",
        "非实时行情；缺失值不补造。仅供研究复盘，不是投资建议或收益预测。",
    ])
