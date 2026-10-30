import pandas as pd
import pytest
import src.importers as importers
from src.importers import read_tabular_upload, validate_stock_pool, save_research_upload, normalize_stock_columns, load_latest_research, stock_pool_template, import_quality_report, infer_import_date, select_market_group_column


def test_infer_import_date_from_exported_data():
    assert infer_import_date(pd.DataFrame({"交易日期": ["2026-09-18", "2026-09-18"], "代码": ["1", "2"]})) == "2026-09-18"


def test_import_quality_report_distinguishes_coverage_and_missing_fields():
    report = import_quality_report(pd.DataFrame({
        "\u4ee3\u7801": ["000001", "000002", "000003"], "\u540d\u79f0": ["A", "B", "C"],
        "\u4ef7\u683c": [1.0, 0.0, None], "\u6da8\u8dcc\u5e45": [1.0, None, -2.0],
        "\u6210\u4ea4\u989d": [100, None, 300],
    }))
    assert report["rows"] == 3
    assert report["valid_quotes"] == 1
    assert report["coverage"]["\u4ef7\u683c"] == 1 / 3
    assert report["coverage"]["\u6da8\u8dcc\u5e45"] == 2 / 3
    assert "\u6210\u4ea4\u989d" in report["partial_fields"]
    assert "\u6362\u624b\u7387" in report["missing_fields"]


def test_csv_and_validation():
    raw = b"\xe4\xbb\xa3\xe7\xa0\x81,\xe5\x90\x8d\xe7\xa7\xb0,\xe6\x9d\xbf\xe5\x9d\x97\n688008,\xe6\xbe\x9c\xe8\xb5\xb7\xe7\xa7\x91\xe6\x8a\x80,\xe5\x8d\x8a\xe5\xaf\xbc\xe4\xbd\x93\n"
    df = read_tabular_upload(raw, "pool.csv")
    assert validate_stock_pool(df) == []


def test_unsupported_file():
    with pytest.raises(ValueError):
        read_tabular_upload(b"x", "pool.txt")


def test_tonghuashun_wrapped_text_extracts_stock_identity():
    raw = "\u4ee3\u7801\t\u540d\u79f0\t\u73b0\u4ef7\n600584\t\u957f\u7535\u79d1\u6280\n688820\t\u76db\u5408\u6676\u5fae\n".encode("gb18030")
    df = read_tabular_upload(raw, "Table.txt")
    assert list(df["\u4ee3\u7801"]) == ["600584", "688820"]
    assert list(df["\u540d\u79f0"]) == ["\u957f\u7535\u79d1\u6280", "\u76db\u5408\u6676\u5fae"]
    assert "\u677f\u5757" in df.columns


def test_tonghuashun_full_market_export_keeps_breadth_fields():
    header = [""] * 21
    header[2], header[4], header[8], header[10], header[20] = "\u4ee3\u7801", "\u540d\u79f0", "\u6da8\u5e45", "\u73b0\u4ef7", "\u603b\u91d1\u989d"
    row = [""] * 19
    row[2], row[3], row[6], row[8], row[18] = "SH688008", "\u6f9c\u8d77\u79d1\u6280", "+3.28%", "216.38", "25.54\u4ebf"
    raw = ("\t".join(header) + "\r\n" + "\t".join(row) + "\r\n").encode("gb18030")
    df = read_tabular_upload(raw, "market.txt")
    assert df.iloc[0]["\u6da8\u8dcc\u5e45"] == 3.28
    assert df.iloc[0]["\u4ef7\u683c"] == 216.38
    assert df.iloc[0]["\u6210\u4ea4\u989d"] == 2_554_000_000


def test_normalize_keeps_exchange_board_and_industry_separate():
    raw = pd.DataFrame({
        "\u4ee3\u7801": ["SH688008"], "\u540d\u79f0": ["\u6f9c\u8d77\u79d1\u6280"], "\u677f\u5757": ["\u79d1\u521b\u677f"],
        "\u6240\u5c5e\u884c\u4e1a": ["\u534a\u5bfc\u4f53"], "\u7ec6\u5206\u884c\u4e1a": ["\u5b58\u50a8\u82af\u7247"],
        "\u73b0\u4ef7": ["216.38"], "\u6da8\u5e45": ["+3.28%"], "\u603b\u91d1\u989d": ["25.54\u4ebf"],
    })
    out = normalize_stock_columns(raw)
    assert out.iloc[0]["\u677f\u5757"] == "\u79d1\u521b\u677f"
    assert out.iloc[0]["\u884c\u4e1a"] == "\u534a\u5bfc\u4f53"
    assert out.iloc[0]["\u7ec6\u5206\u884c\u4e1a"] == "\u5b58\u50a8\u82af\u7247"
    assert out.iloc[0]["\u6210\u4ea4\u989d"] == 2_554_000_000


def test_normalize_discards_numeric_cells_misparsed_as_industry_labels():
    raw = pd.DataFrame({
        "\u4ee3\u7801": ["SH688837"], "\u540d\u79f0": ["\u4fe1\u8bfa\u7ef4"], "\u677f\u5757": ["\u79d1\u521b\u677f"],
        "\u884c\u4e1a": ["47.57"], "\u7ec6\u5206\u884c\u4e1a": ["27.60"], "\u91cf\u6bd4": ["43.15"],
    })
    out = normalize_stock_columns(raw)
    assert out.iloc[0]["\u884c\u4e1a"] == ""
    assert out.iloc[0]["\u7ec6\u5206\u884c\u4e1a"] == ""
    assert out.iloc[0]["\u677f\u5757"] == "\u79d1\u521b\u677f"


def test_select_market_group_prefers_sufficiently_covered_detail_industry():
    frame = pd.DataFrame({
        "\u677f\u5757": ["\u4e3b\u677f"] * 5,
        "\u884c\u4e1a": ["", "", "", "\u534a\u5bfc\u4f53", ""],
        "\u7ec6\u5206\u884c\u4e1a": ["\u5b58\u50a8\u82af\u7247", "\u5b58\u50a8\u82af\u7247", "", "\u901a\u4fe1\u8bbe\u5907", ""],
    })
    assert select_market_group_column(frame) == "\u7ec6\u5206\u884c\u4e1a"


def test_market_map_hierarchy_path_keeps_industry_above_subindustry():
    from src.importers import market_map_hierarchy_path

    frame = pd.DataFrame({
        "行业": ["电子", "电子", "通信"],
        "细分行业": ["PCB", "存储", "光模块"],
    })

    assert market_map_hierarchy_path(frame, "细分行业") == ["行业", "细分行业"]
    assert market_map_hierarchy_path(frame, "行业") == ["行业"]


def test_market_map_hierarchy_path_skips_sparse_parent_industry():
    from src.importers import market_map_hierarchy_path

    frame = pd.DataFrame({
        "行业": ["电子"] + [""] * 19,
        "细分行业": ["半导体"] * 20,
    })

    assert market_map_hierarchy_path(frame, "细分行业") == ["细分行业"]


def test_market_group_display_mask_hides_blank_and_unclassified_by_default():
    frame = pd.DataFrame({"细分行业": ["半导体", "", "未分类", "通信设备", None]})
    assert importers.market_group_display_mask(frame, "细分行业").tolist() == [True, False, False, True, False]
    assert importers.market_group_display_mask(frame, "细分行业", include_unclassified=True).tolist() == [True, True, True, True, True]


def test_market_group_coverage_reports_classification_completeness():
    frame = pd.DataFrame({"细分行业": ["半导体", "", "未分类", "通信设备"]})
    result = importers.market_group_coverage(frame, "细分行业")
    assert result == {"total": 4, "classified": 2, "unclassified": 2, "coverage": 0.5}


def test_valid_peer_group_fields_ignores_unclassified_industry_labels():
    frame = pd.DataFrame({
        "板块": ["主板"],
        "行业": ["未分类"],
        "细分行业": [""],
    })
    assert importers.valid_peer_group_fields(frame, 0, ["细分行业", "板块", "行业"]) == ["板块"]


def test_market_navigation_level_uses_the_field_containing_the_selected_group():
    frame = pd.DataFrame({
        "板块": ["主板", "创业板"],
        "行业": ["电子", "通信"],
        "细分行业": ["半导体", "通信设备"],
    })
    assert importers.market_navigation_level(frame, "半导体", fallback="板块") == "细分行业"
    assert importers.market_navigation_level(frame, "电子", fallback="板块") == "行业"
    assert importers.market_navigation_level(frame, "不存在", fallback="板块") == "板块"


def test_researchable_market_groups_excludes_single_stock_groups():
    grouped = pd.DataFrame({"分类": ["半导体", "锂电池", "通信设备"], "股票数": [56, 1, 17]})
    result = importers.researchable_market_groups(grouped, minimum_samples=3)
    assert result["分类"].tolist() == ["半导体", "通信设备"]


def test_load_research_history_keeps_snapshot_dates(tmp_path):
    from src.importers import load_research_history
    first = pd.DataFrame({"代码": ["000001"], "名称": ["甲"], "交易日期": ["2026-09-24"], "涨跌幅": [1.0]})
    second = pd.DataFrame({"代码": ["000002"], "名称": ["乙"], "交易日期": ["2026-09-25"], "涨跌幅": [-1.0]})
    first.to_csv(tmp_path / "stock_pool_a.csv", index=False, encoding="utf-8-sig")
    second.to_csv(tmp_path / "stock_pool_b.csv", index=False, encoding="utf-8-sig")

    result = load_research_history(str(tmp_path))

    assert result["快照日期"].drop_duplicates().tolist() == ["2026-09-24", "2026-09-25"]


def test_watchlist_upload_does_not_replace_same_day_market_quotes(tmp_path):
    quotes = pd.DataFrame({"代码": ["000001", "000002"], "名称": ["甲", "乙"], "交易日期": ["2026-09-25"] * 2, "涨跌幅": [1.0, -2.0]})
    watchlist = pd.DataFrame({"代码": ["000003"], "名称": ["丙"], "交易日期": ["2026-09-25"]})
    quotes.to_csv(tmp_path / "a.csv", index=False, encoding="utf-8-sig")
    watchlist.to_csv(tmp_path / "b.csv", index=False, encoding="utf-8-sig")
    history = importers.load_research_history(str(tmp_path))
    assert history["代码"].tolist() == ["000001", "000002"]
    latest, trade_date = importers.latest_quote_snapshot(history)
    assert trade_date == "2026-09-25"
    assert latest["代码"].tolist() == ["000001", "000002"]


def test_quote_less_watchlist_does_not_create_market_history_date(tmp_path):
    watchlist = pd.DataFrame({"代码": ["000003"], "名称": ["丙"], "交易日期": ["2026-09-26"]})
    watchlist.to_csv(tmp_path / "watchlist.csv", index=False, encoding="utf-8-sig")
    history = importers.load_research_history(str(tmp_path))
    assert history.empty
    assert importers.latest_quote_snapshot(history) == (None, None)


def test_smaller_quoted_watchlist_does_not_replace_full_market_snapshot(tmp_path):
    full_market = pd.DataFrame({"代码": ["000001", "000002"], "名称": ["甲", "乙"], "交易日期": ["2026-09-25"] * 2, "涨跌幅": [1.0, -2.0]})
    smaller = pd.DataFrame({"代码": ["000003"], "名称": ["丙"], "交易日期": ["2026-09-25"], "涨跌幅": [3.0]})
    full_market.to_csv(tmp_path / "a.csv", index=False, encoding="utf-8-sig")
    smaller.to_csv(tmp_path / "b.csv", index=False, encoding="utf-8-sig")
    history = importers.load_research_history(str(tmp_path))
    assert history["代码"].tolist() == ["000001", "000002"]


def test_save_research_upload_creates_timestamped_file(tmp_path):
    path = save_research_upload(pd.DataFrame({"代码": ["688008"]}), str(tmp_path), "pool")
    assert path.endswith(".csv")
    assert pd.read_csv(path, encoding="utf-8-sig").iloc[0]["代码"] == 688008


def test_normalize_and_load_latest(tmp_path):
    raw = pd.DataFrame({"股票代码": [688008], "股票名称": ["澜起科技"], "现价": [216.38]})
    save_research_upload(raw, str(tmp_path), "pool")
    loaded = load_latest_research(str(tmp_path))
    assert loaded.iloc[0]["代码"] == "688008"
    assert loaded.iloc[0]["价格"] == 216.38


def test_normalize_percent_values_and_template():
    loaded = normalize_stock_columns(pd.DataFrame({"代码": [688008], "名称": ["澜起科技"], "涨幅": ["+3.28%"]}))
    assert loaded.iloc[0]["涨跌幅"] == 3.28
    assert "代码" in stock_pool_template().columns


def test_capital_replay_template_has_timestamp_industry_and_net_flow_fields():
    template = importers.capital_replay_template()
    assert {"时间", "行业", "净流入额", "涨跌幅", "成交额"}.issubset(template.columns)


def test_normalize_capital_replay_accepts_template_fields_and_numeric_values():
    raw = pd.DataFrame({
        "时间": ["2026-09-24 09:35", "2026-09-24 09:35"],
        "行业": ["半导体", "通信设备"],
        "净流入额": ["1.25亿", "-3200万"],
        "涨跌幅": ["+2.15%", "-0.45%"],
        "成交额": ["8.4亿", "3.2亿"],
    })
    normalized = importers.normalize_capital_replay(raw)
    assert importers.validate_capital_replay(normalized) == []
    assert normalized["净流入额"].tolist() == [125_000_000.0, -32_000_000.0]
    assert normalized["涨跌幅"].tolist() == [2.15, -0.45]


def test_load_capital_replay_combines_saved_snapshots(tmp_path):
    replay = pd.DataFrame({"时间": ["2026-09-24 09:35"], "行业": ["半导体"], "净流入额": [1.0]})
    importers.save_capital_replay(replay, str(tmp_path))
    loaded = importers.load_capital_replay(str(tmp_path))
    assert len(loaded) == 1
    assert loaded.iloc[0]["行业"] == "半导体"


def test_capital_replay_industry_track_orders_points_by_time():
    replay = pd.DataFrame({
        "时间": ["2026-09-24 14:50", "2026-09-24 09:35", "2026-09-24 09:35"],
        "行业": ["半导体", "半导体", "通信设备"],
        "净流入额": [300.0, 100.0, 50.0],
    })
    track = importers.capital_replay_industry_track(replay, "半导体")
    assert track["时间"].tolist() == ["2026-09-24 09:35", "2026-09-24 14:50"]
    assert track["净流入额"].tolist() == [100.0, 300.0]


def test_capital_replay_flow_changes_compares_first_and_last_timepoints():
    replay = pd.DataFrame({
        "时间": ["2026-09-24 09:35", "2026-09-24 14:50", "2026-09-24 09:35", "2026-09-24 14:50"],
        "行业": ["半导体", "半导体", "通信设备", "通信设备"],
        "净流入额": [100.0, 300.0, 200.0, -100.0],
    })
    changes = importers.capital_replay_flow_changes(replay)
    assert changes.loc[changes["行业"].eq("半导体"), "净流入变化"].iloc[0] == 200.0
    assert changes.loc[changes["行业"].eq("通信设备"), "净流入变化"].iloc[0] == -300.0


def test_capital_replay_readiness_reports_complete_industry_tracks():
    replay = pd.DataFrame({
        "时间": ["2026-09-24 09:35", "2026-09-24 14:50", "2026-09-24 09:35"],
        "行业": ["半导体", "半导体", "通信设备"],
        "净流入额": [100.0, 300.0, 200.0],
    })

    result = importers.capital_replay_readiness(replay)

    assert result["时点数"] == 2
    assert result["行业数"] == 2
    assert result["完整轨迹行业"] == 1
    assert result["完整轨迹占比"] == pytest.approx(0.5)


def test_filter_capital_replay_by_date_keeps_one_trading_day():
    replay = pd.DataFrame({
        "时间": ["2026-09-23 14:50", "2026-09-24 09:35", "2026-09-24 14:50"],
        "行业": ["半导体", "半导体", "半导体"],
        "净流入额": [10.0, 20.0, 30.0],
    })
    filtered = importers.filter_capital_replay_by_date(replay, "2026-09-24")
    assert filtered["时间"].tolist() == ["2026-09-24 09:35", "2026-09-24 14:50"]


def test_select_research_snapshot_uses_only_requested_trade_day():
    data = {
        "stocks": pd.DataFrame({"代码": ["000003"], "涨跌幅": [3.0]}),
        "market_history": pd.DataFrame({
            "快照日期": ["2026-09-24", "2026-09-25", "2026-09-25"],
            "代码": ["000001", "000002", "000003"],
            "涨跌幅": [1.0, 2.0, 3.0],
        }),
        "import_date": "2026-09-25",
        "stock_quote_source": "imported",
    }

    selected = importers.select_research_snapshot(data, "2026-09-24")

    assert selected["stocks"]["代码"].tolist() == ["000001"]
    assert selected["import_date"] == "2026-09-24"
    assert selected["stock_quote_source"] == "imported"
    assert data["stocks"]["代码"].tolist() == ["000003"]


def test_select_research_snapshot_rejects_missing_or_unquoted_date():
    data = {
        "stocks": pd.DataFrame({"代码": ["000003"], "涨跌幅": [3.0]}),
        "market_history": pd.DataFrame({
            "快照日期": ["2026-09-24", "2026-09-25"],
            "代码": ["000001", "000002"],
            "涨跌幅": [None, 2.0],
        }),
        "import_date": "2026-09-25",
    }

    assert importers.available_quote_snapshot_dates(data["market_history"]) == ["2026-09-25"]
    assert importers.select_research_snapshot(data, "2026-09-24") is data
    assert importers.select_research_snapshot(data, "2026-09-23") is data


def test_capital_replay_snapshot_map_uses_turnover_or_flow_magnitude_for_area():
    snapshot = pd.DataFrame({
        "行业": ["半导体", "通信设备"],
        "净流入额": [100.0, -50.0],
        "成交额": [1000.0, 0.0],
    })
    mapped = importers.capital_replay_snapshot_map(snapshot)
    assert mapped.loc[mapped["行业"].eq("半导体"), "面积"].iloc[0] == 1000.0
    assert mapped.loc[mapped["行业"].eq("通信设备"), "面积"].iloc[0] == 50.0


def test_quote_normalization_keeps_numeric_ohlc_aliases_and_missing_values():
    frame = pd.DataFrame({"证券代码": ["000001"], "股票名称": ["甲"],
                          "昨收价": ["10.25"], "开盘价": ["10.50"],
                          "最高价": ["11.00"], "最低价": ["--"]})
    result = importers.normalize_stock_columns(frame)
    assert result.loc[0, "昨收"] == 10.25
    assert result.loc[0, "今开"] == 10.50
    assert result.loc[0, "最高"] == 11.00
    assert pd.isna(result.loc[0, "最低"])


def test_ths_text_retains_ohlc_for_quote_cards():
    content = "代码\t名称\t现价\t昨收\t今开\t最高\t最低\nSH600001\t甲公司\t12\t10\t11\t13\t--\n"
    raw = importers.read_tabular_upload(content.encode("gb18030"), "Table.txt")
    normalized = importers.normalize_stock_columns(raw)
    assert normalized.loc[0, "代码"] == "600001"
    assert normalized.loc[0, "今开"] == 11
    assert normalized.loc[0, "最高"] == 13
    assert pd.isna(normalized.loc[0, "最低"])
