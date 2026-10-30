"""Visible cloud-map scope, separate from full-market breadth."""
import pandas as pd


def cloud_scope_audit(stocks, size_field, displayed_count):
    changes = pd.to_numeric(stocks.get('涨跌幅', pd.Series(index=stocks.index, dtype=float)), errors='coerce')
    valid = changes.notna()
    area_valid = pd.Series(True, index=stocks.index) if size_field == '等权' else pd.to_numeric(
        stocks.get(size_field, pd.Series(index=stocks.index, dtype=float)), errors='coerce').gt(0)
    eligible = int((valid & area_valid).sum())
    return {'范围样本': len(stocks), '有效涨跌': int(valid.sum()), '未知涨跌': int((~valid).sum()),
            '可绘制样本': eligible, '面积无效': int((valid & ~area_valid).sum()),
            '实际显示': displayed_count, '抽样未显示': max(0, eligible-displayed_count)}


def cloud_scope_summary(leaves):
    changes = pd.to_numeric(leaves.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
    return {"样本": len(leaves), "有效涨跌": len(changes),
            "上涨": int((changes > 0).sum()), "下跌": int((changes < 0).sum()),
            "平盘": int(changes.eq(0).sum()),
            "平均涨跌": float(changes.mean()) if len(changes) else None}


def cloud_scope_export(leaves, *, date, area, color, source=None):
    result = leaves.copy().reset_index(drop=True)
    if "个股" in result:
        result.insert(0, "代码", result["个股"].astype(str).str.split(" · ", n=1).str[0])
    from .public_workspace.detail_model import quote_export
    return quote_export(result.assign(快照日期=date or "未提供", 面积口径=area, 颜色口径=color),
                        {'import_date': date, 'stock_quote_source': source})
