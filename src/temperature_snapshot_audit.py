"""Descriptive audit of imported market snapshots, never a scoring feed."""

from pathlib import Path
import hashlib
import json
import re

import numpy as np
import pandas as pd


def audit_imported_snapshots(directory, start='2026-10-12', end=None):
    """Return source-limited facts with explicit data quality and scope."""
    directory = Path(directory)
    rows = []
    sidecar_path = directory.parent / 'temperature' / 'import_snapshot_audit_20261016.json'
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        sidecar = {}
    for path in sorted(directory.glob('stock_pool_*.csv')):
        match = re.search(r'stock_pool_(\d{8})_', path.name)
        if not match:
            continue
        day = pd.Timestamp(match[1]).date().isoformat()
        if day < start or (end and day > end):
            continue
        frame = pd.read_csv(path, dtype={'代码': str}, low_memory=False)
        required = {'代码', '交易日期', '价格', '昨收', '涨跌幅', '成交量', '成交额'}
        if not required.issubset(frame) or frame.empty:
            continue
        codes = frame['代码'].astype(str).str.fullmatch(r'\d{6}')
        dates = frame['交易日期'].astype(str).eq(day)
        price = pd.to_numeric(frame['价格'], errors='coerce')
        previous = pd.to_numeric(frame['昨收'], errors='coerce')
        change = pd.to_numeric(frame['涨跌幅'], errors='coerce')
        volume = pd.to_numeric(frame['成交量'], errors='coerce')
        amount = pd.to_numeric(frame['成交额'], errors='coerce')
        valid = (codes & dates & price.gt(0) & previous.gt(0) &
                 change.map(np.isfinite) & volume.gt(0) & amount.ge(0))
        expected_change = price.div(previous).sub(1).mul(100)
        inconsistent = valid & change.sub(expected_change).abs().gt(.06)
        limit_fields = {'涨停价', '跌停价'}.issubset(frame)
        raw_source = all(field in frame and frame[field].notna().any()
                         for field in ('导入源文件', '源文件SHA256', '源文件修改时间'))
        source_time = None
        if raw_source:
            source_time = pd.to_datetime(frame['源文件修改时间'].dropna().iloc[0], errors='coerce')
        elif (path.name == sidecar.get('snapshot_file') and
              hashlib.sha256(path.read_bytes()).hexdigest() == sidecar.get('snapshot_sha256') and
              sidecar.get('same_codes') and sidecar.get('price_mismatches') == 0):
            source_time = pd.Timestamp(sidecar['source_modified_at'])
            raw_source = True
        before_close = (pd.notna(source_time) and source_time is not None and
                        source_time.hour < 15)
        rows.append({
            '数据期': day,
            '导入股票数': len(frame),
            '有效交易样本': int(valid.sum()),
            '上涨占比': float(change[valid].gt(0).mean() * 100) if valid.any() else None,
            '样本成交额（万亿元）': float(amount[valid].sum() / 1e12),
            '价格涨幅不一致': int(inconsistent.sum()),
            '代码重复': int(frame['代码'].duplicated().sum()),
            '日期不符': int((~dates).sum()),
            '原始文件信息': '有' if raw_source else '缺',
            '源文件时刻': source_time.isoformat() if source_time is not None and pd.notna(source_time) else '未知',
            '时点风险': '收盘前' if before_close else '未发现收盘前' if source_time is not None and pd.notna(source_time) else '待核验',
            '涨跌停价': '有' if limit_fields else '缺',
            '文件': path.name,
        })
    return pd.DataFrame(rows)
