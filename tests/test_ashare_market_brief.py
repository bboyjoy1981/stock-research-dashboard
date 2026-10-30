from datetime import date

from src.ashare_market_brief import AshareMarketBriefService, format_ashare_daily_brief


def test_daily_brief_uses_current_local_snapshot_before_public_fetch(tmp_path):
    (tmp_path / "snapshot.csv").write_text(
        "代码,名称,交易日期,价格,涨跌幅,成交量,成交额\n688008,澜起科技,2026-09-28,100,2.5,1000,200000\n",
        encoding="utf-8-sig",
    )
    calls = []
    service = AshareMarketBriefService(tmp_path, fetch_json=lambda _url: calls.append(_url) or {}, today=lambda: date(2026, 9, 28))

    brief = service.fetch_daily_brief()

    assert brief.source == "本地快照"
    assert brief.snapshot_date == "2026-09-28"
    assert calls == []


def test_daily_brief_falls_back_to_four_public_indices_when_local_snapshot_is_stale(tmp_path):
    (tmp_path / "snapshot.csv").write_text(
        "代码,名称,交易日期,价格,涨跌幅\n688008,澜起科技,2026-09-27,100,2.5\n",
        encoding="utf-8-sig",
    )
    payload = {"data": {"diff": [
        {"f12": "000001", "f14": "上证指数", "f2": 3200.0, "f3": 0.5, "f4": 16.0, "f5": 100.0, "f6": 200.0},
        {"f12": "399001", "f14": "深证成指", "f2": 10000.0, "f3": -0.2, "f4": -20.0, "f5": 110.0, "f6": 210.0},
        {"f12": "399006", "f14": "创业板指", "f2": 2000.0, "f3": 0.1, "f4": 2.0, "f5": 120.0, "f6": 220.0},
        {"f12": "000688", "f14": "科创50", "f2": 900.0, "f3": 1.0, "f4": 9.0, "f5": 130.0, "f6": 230.0},
    ]}}
    service = AshareMarketBriefService(tmp_path, fetch_json=lambda _url: payload, today=lambda: date(2026, 9, 28))

    brief = service.fetch_daily_brief()
    text = format_ashare_daily_brief(brief)

    assert brief.source == "公开行情"
    assert [item.label for item in brief.indices] == ["上证指数", "深证成指", "创业板指", "科创50"]
    assert brief.total_volume == 460.0
    assert brief.total_amount == 860.0
    assert "两市成交量" in text and "两市成交额" in text
    assert "仅供研究参考，不构成投资建议。" in text


def test_daily_brief_does_not_present_weekend_data_as_current(tmp_path):
    service = AshareMarketBriefService(tmp_path, fetch_json=lambda _url: {"data": {"diff": []}}, today=lambda: date(2026, 9, 27))

    text = format_ashare_daily_brief(service.fetch_daily_brief())

    assert "非交易日" in text


def test_formatter_marks_unavailable_market_breadth_limit_counts_and_sectors(tmp_path):
    service = AshareMarketBriefService(tmp_path, fetch_json=lambda _url: {"data": {"diff": []}}, today=lambda: date(2026, 9, 28))

    text = format_ashare_daily_brief(service.fetch_daily_brief())

    assert "市场宽度：获取失败" in text
    assert "涨停/跌停：获取失败" in text
    assert "板块强弱：获取失败" in text


def test_daily_brief_retries_once_after_an_empty_public_response(tmp_path):
    payloads = [
        {"data": {"diff": []}},
        {"data": {"diff": [{"f14": "上证指数", "f2": 3200, "f3": 0.5, "f4": 16, "f5": 100, "f6": 200}]}},
    ]
    service = AshareMarketBriefService(tmp_path, fetch_json=lambda _url: payloads.pop(0), today=lambda: date(2026, 9, 28))

    brief = service.fetch_daily_brief()

    assert brief.indices[0].price == 3200
    assert payloads == []


def test_daily_brief_uses_backup_index_source_when_primary_stays_empty(tmp_path):
    backup = '\n'.join(
        (
            'v_s_sh000001="1~上证指数~000001~3200~16~0.5~100~200~~0~ZS~";',
            'v_s_sz399001="51~深证成指~399001~10000~-20~-0.2~110~210~~0~ZS~";',
            'v_s_sz399006="51~创业板指~399006~2000~2~0.1~120~220~~0~ZS~";',
            'v_s_sh000688="1~科创50~000688~900~9~1~130~230~~0~ZS~";',
        )
    )
    service = AshareMarketBriefService(
        tmp_path,
        fetch_json=lambda _url: {"data": {"diff": []}},
        fetch_text=lambda _url: backup,
        today=lambda: date(2026, 9, 28),
    )

    brief = service.fetch_daily_brief()

    assert brief.source == "备用公开行情"
    assert [item.price for item in brief.indices] == [3200, 10000, 2000, 900]
    assert brief.total_volume is None
    assert brief.total_amount is None
