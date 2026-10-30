import pandas as pd
from src.calculations import calculate_market_score, market_regime, position_targets, calculate_position_status
import pytest


def test_stock_snapshot_history_orders_deduplicates_and_caps_replay_date():
    from src.calculations import stock_snapshot_history

    snapshots = pd.DataFrame([
        {"快照日期": "2026-09-17", "代码": "000001", "价格": 12, "涨跌幅": 2, "成交额": 200},
        {"快照日期": "2026-09-16", "代码": "1.0", "价格": 10, "涨跌幅": -1, "成交额": 100},
        {"快照日期": "2026-09-17", "代码": "000001", "价格": 13, "涨跌幅": 3, "成交额": 250},
        {"快照日期": "2026-09-18", "代码": "000001", "价格": 14, "涨跌幅": 4, "成交额": 300},
        {"快照日期": "2026-09-16", "代码": "000002", "价格": 30, "涨跌幅": 5, "成交额": 400},
    ])
    result = stock_snapshot_history(snapshots, "000001", through_date="2026-09-17")

    assert result["交易日"].tolist() == ["2026-09-16", "2026-09-17"]
    assert result["价格"].tolist() == [10, 13]
    assert result["成交额"].tolist() == [100, 250]


def test_stock_snapshot_history_keeps_missing_values_unknown():
    from src.calculations import stock_snapshot_history

    result = stock_snapshot_history(pd.DataFrame([
        {"快照日期": "2026-09-16", "代码": "600001", "涨跌幅": "1.5"},
    ]), "600001")

    assert len(result) == 1
    assert pd.isna(result.iloc[0]["价格"])
    assert result.iloc[0]["涨跌幅"] == 1.5


def test_research_context_label_builds_a_safe_market_breadcrumb():
    from src.calculations import research_context_label

    assert research_context_label({"source": "市场总览", "industry": "半导体"}) == "当前研究路径：市场总览 → 半导体"
    assert research_context_label({"industry": "PCB"}) == "当前研究路径：PCB"
    assert research_context_label({}) is None


def test_research_context_stock_filter_prefers_the_selected_industry():
    import pandas as pd
    from src.calculations import filter_stocks_by_research_context

    stocks = pd.DataFrame({
        "代码": ["000001", "000002", "000003"],
        "行业": ["半导体", "银行", "半导体"],
        "细分行业": ["存储芯片", "国有银行", "封装测试"],
    })
    result = filter_stocks_by_research_context(stocks, {"industry": "半导体"}, ["行业", "细分行业"])

    assert result["代码"].tolist() == ["000001", "000003"]


def test_market_sector_turnover_never_substitutes_market_cap_for_turnover():
    from src.calculations import market_sector_turnover

    stocks = pd.DataFrame({"行业": ["半导体", "半导体", "银行"], "流通市值": [1000, 2000, 3000]})
    result = market_sector_turnover(stocks, "行业")

    assert result["行业"].tolist() == ["半导体", "银行"]
    assert result["成交额"].isna().all()


def test_market_sector_turnover_leaves_groups_without_reported_amount_unknown():
    from src.calculations import market_sector_turnover

    stocks = pd.DataFrame({"行业": ["半导体", "半导体", "银行"], "成交额": [100.0, None, None]})
    result = market_sector_turnover(stocks, "行业").set_index("行业")

    assert result.loc["半导体", "成交额"] == 100.0
    assert pd.isna(result.loc["银行", "成交额"])


def test_market_snapshot_comparison_reports_stage_and_position_shift():
    from src.calculations import compare_market_snapshots
    previous = {"score": 2, "stage": "\u5f31\u52bf\u9707\u8361", "breadth": {"advance_ratio": .42}}
    current = {"score": 5, "stage": "\u4e3b\u5347\u9636\u6bb5", "breadth": {"advance_ratio": .68}}
    result = compare_market_snapshots(current, previous, 1_000_000)
    assert result["score_delta"] == 3
    assert result["stage_changed"] is True
    assert result["position_low_delta"] == pytest.approx(400_000)
    assert result["position_high_delta"] == pytest.approx(450_000)
    assert result["advance_ratio_delta"] == pytest.approx(.26)


def test_market_snapshot_comparison_without_history_has_no_false_delta():
    from src.calculations import compare_market_snapshots
    result = compare_market_snapshots({"score": 1, "stage": "\u7cfb\u7edf\u98ce\u9669"}, None, 1_000_000)
    assert result["previous"] is None


def test_portfolio_risk_summary_keeps_missing_single_stock_stops_visible():
    from src.calculations import portfolio_risk_summary
    rows = [
        {"amount": 100_000, "stop_pct": .12},
        {"amount": 50_000, "stop_pct": None},
    ]
    result = portfolio_risk_summary(rows, 1_000_000)
    assert result["market_value"] == 150_000
    assert result["estimated_loss"] == 12_000
    assert result["unprotected_positions"] == 1
    assert result["risk_ratio"] == pytest.approx(.012)


def test_score_and_regime():
    assert calculate_market_score([1, 0, 1, 1, 0, 1]) == 4
    assert market_regime(4)["name"] == "修复阶段"


def test_position_targets_and_status():
    targets = position_targets(1_100_000, "主升阶段")
    assert targets["total_low"] == 880_000
    assert calculate_position_status(300_000, 1_100_000, .15, .25) == "超配"


def test_compare_stock_pool_preserves_order_and_caps_at_six():
    import pandas as pd
    from src.calculations import compare_stock_pool
    frame = pd.DataFrame({"代码": ["000001", "000002", "000003", "000004", "000005", "000006", "000007"], "名称": list("ABCDEFG")})
    result = compare_stock_pool(frame, ["000006", "000002", "000007", "000001", "000003", "000004", "000005"])
    assert result["代码"].tolist() == ["000006", "000002", "000007", "000001", "000003", "000004"]


def test_compare_stock_pool_handles_empty_or_missing_code_column():
    import pandas as pd
    from src.calculations import compare_stock_pool
    assert compare_stock_pool(pd.DataFrame(), ["000001"]).empty
    assert compare_stock_pool(pd.DataFrame({"名称": ["测试"]}), ["000001"]).empty


def test_market_close_summary_reports_breadth_status():
    import pandas as pd
    from src.calculations import market_close_summary
    result = market_close_summary(pd.DataFrame({"涨跌幅": [1.0, 2.0, -0.2], "成交额": [10, 20, 30]}))
    assert result["status"] == "偏强"
    assert result["up"] == 2
    assert result["amount_sum"] == 60


def test_market_component_extremes_returns_leader_laggard_and_most_active_stock():
    import pandas as pd
    from src.calculations import market_component_extremes
    frame = pd.DataFrame({
        "代码": ["000001", "000002", "000003"],
        "名称": ["甲", "乙", "丙"],
        "涨跌幅": [1.2, 6.8, -3.4],
        "成交额": [200, 120, 500],
    })
    result = market_component_extremes(frame)
    assert result["leader"]["代码"] == "000002"
    assert result["laggard"]["代码"] == "000003"
    assert result["active"]["代码"] == "000003"


def test_market_map_leaves_keep_stock_tiles_and_apply_group_strength_color():
    import pandas as pd
    from src.calculations import market_map_leaves
    stocks = pd.DataFrame({
        "代码": ["000001", "000002", "000003"],
        "名称": ["甲", "乙", "丙"],
        "行业": ["半导体", "半导体", "通信"],
        "涨跌幅": [1.2, -0.8, 3.5],
        "成交额": [100, 200, 300],
    })
    grouped = pd.DataFrame({"行业": ["半导体", "通信"], "行业强度": [81, 62]})
    result = market_map_leaves(stocks, grouped, "行业", "成交额", "行业强度")
    assert result["个股"].tolist() == ["000001 · 甲", "000002 · 乙", "000003 · 丙"]
    assert result["云图标签"].tolist() == ["甲\n+1.20%", "乙\n-0.80%", "丙\n+3.50%"]
    assert result["面积"].tolist() == [100.0, 200.0, 300.0]
    assert result["云图颜色"].tolist() == [81.0, 81.0, 62.0]


def test_market_map_area_options_require_positive_reported_values():
    from src.calculations import market_map_area_options

    stocks = pd.DataFrame({"成交额": [None, 0], "流通市值": [100, None], "总市值": [-1, 0]})

    assert market_map_area_options(stocks) == ["流通市值"]
    assert market_map_area_options(pd.DataFrame({"涨跌幅": [1.0, -1.0]})) == ["等权"]


def test_market_map_leaves_keep_requested_parent_field_for_three_level_map():
    from src.calculations import market_map_leaves
    stocks = pd.DataFrame({
        "行业": ["电子", "电子"],
        "细分行业": ["PCB", "存储"],
        "名称": ["甲", "乙"],
        "涨跌幅": [1.0, -1.0],
        "成交额": [100, 200],
    })
    grouped = pd.DataFrame({"细分行业": ["PCB", "存储"], "行业强度": [80, 60]})

    result = market_map_leaves(stocks, grouped, "细分行业", "成交额", "行业强度", parent_field="行业")

    assert result["行业"].tolist() == ["电子", "电子"]


def test_market_map_leaves_use_parent_when_subindustry_names_repeat():
    import pandas as pd
    from src.calculations import market_map_leaves

    stocks = pd.DataFrame({
        "行业": ["电子", "通信"], "细分行业": ["设备", "设备"],
        "代码": ["000001", "000002"], "名称": ["甲", "乙"],
        "涨跌幅": [2.0, -1.0], "成交额": [100.0, 200.0],
    })
    grouped = pd.DataFrame({
        "行业": ["电子", "通信"], "细分行业": ["设备", "设备"],
        "行业强度": [80.0, 20.0],
    })

    result = market_map_leaves(stocks, grouped, "细分行业", "成交额", "行业强度", parent_field="行业")

    assert result["云图颜色"].tolist() == [80.0, 20.0]


def test_limit_market_map_leaves_keeps_the_most_active_stock_in_each_group():
    import pandas as pd
    from src.calculations import limit_market_map_leaves
    leaves = pd.DataFrame({
        "行业": ["半导体", "半导体", "通信", "通信"],
        "个股": ["甲", "乙", "丙", "丁"],
        "面积": [10, 30, 40, 20],
    })
    result = limit_market_map_leaves(leaves, "行业", maximum_per_group=1)
    assert result["个股"].tolist() == ["乙", "丙"]


def test_limit_market_map_leaves_keeps_each_parent_with_repeated_subindustry():
    import pandas as pd
    from src.calculations import limit_market_map_leaves

    leaves = pd.DataFrame({
        "行业": ["电子", "电子", "通信", "通信"],
        "细分行业": ["设备", "设备", "设备", "设备"],
        "个股": ["甲", "乙", "丙", "丁"],
        "面积": [10, 30, 40, 20],
    })

    result = limit_market_map_leaves(leaves, "细分行业", maximum_per_group=1, parent_field="行业")

    assert result["个股"].tolist() == ["乙", "丙"]


def test_sector_rotation_board_combines_strength_breadth_and_activity():
    import pandas as pd
    from src.calculations import sector_rotation_board

    frame = pd.DataFrame({
        "行业": ["算力", "银行", "医药"],
        "涨跌幅": [3.2, -0.8, 0.5],
        "上涨占比": [0.9, 0.25, 0.6],
        "成交额": [300, 500, 100],
        "股票数": [12, 15, 8],
    })

    result = sector_rotation_board(frame, "行业")

    assert result.iloc[0]["行业"] == "算力"
    assert result.iloc[0]["轮动状态"] == "强势扩散"
    assert result.iloc[0]["轮动热度"] == result["轮动热度"].max()
    assert result.loc[result["行业"] == "银行", "轮动状态"].iloc[0] == "承压"


def test_stock_relative_snapshot_compares_stock_peer_and_market():
    from src.calculations import stock_relative_snapshot

    result = stock_relative_snapshot(3.0, [1.0, -1.0, 2.0], [0.5, 1.5, 2.5])

    assert result["市场平均"] == pytest.approx(2 / 3)
    assert result["同类平均"] == pytest.approx(1.5)
    assert result["相对市场"] == pytest.approx(7 / 3)
    assert result["相对同类"] == pytest.approx(1.5)
    assert result["同类位置"] == pytest.approx(100.0)


def test_index_pulse_snapshot_reports_breadth_and_dispersion():
    import pandas as pd
    from src.calculations import index_pulse_snapshot

    result = index_pulse_snapshot(pd.DataFrame({
        "名称": ["沪深300", "中证1000", "创业板指"],
        "涨跌幅": [1.2, -0.4, 0.8],
    }))

    assert result["上涨数量"] == 2
    assert result["下跌数量"] == 1
    assert result["平均涨跌"] == pytest.approx(0.5333333333)
    assert result["离散度"] == pytest.approx(1.6)
    assert result["最强名称"] == "沪深300"


def test_market_sector_tiers_labels_strength_and_weakness():
    import pandas as pd
    from src.calculations import market_sector_tiers

    result = market_sector_tiers(pd.DataFrame({
        "板块": ["算力", "银行", "医药", "机器人"],
        "涨跌幅": [3.1, -2.2, 0.2, 1.2],
    }), "板块")

    assert result.loc[result["板块"] == "算力", "强弱梯队"].iloc[0] == "强势领涨"
    assert result.loc[result["板块"] == "银行", "强弱梯队"].iloc[0] == "弱势承压"
    assert set(result["强弱梯队"]) == {"强势领涨", "弱势承压", "震荡观察", "偏强跟随"}


def test_industry_chain_summary_aggregates_matching_members():
    import pandas as pd
    from src.calculations import industry_chain_summary

    frame = pd.DataFrame({
        "行业": ["半导体", "PCB", "银行"],
        "涨跌幅": [2.0, -1.0, 0.5],
        "成交额": [100, 200, 300],
    })
    result = industry_chain_summary(
        frame,
        {"芯片链": ("半导体", "PCB"), "金融": ("银行",)},
        ["行业"],
    )

    chip = result.loc[result["产业链"] == "芯片链"].iloc[0]
    assert chip["股票数"] == 2
    assert chip["平均涨跌"] == pytest.approx(0.5)
    assert chip["上涨占比"] == pytest.approx(0.5)
    assert chip["成交额"] == pytest.approx(300)


def test_market_close_review_summarizes_breadth_extremes_and_leader():
    import pandas as pd
    from src.calculations import market_close_review

    stocks = pd.DataFrame({"涨跌幅": [4.0, 1.0, -2.0, 10.0, -10.0]})
    sectors = pd.DataFrame({"行业": ["算力", "银行"], "涨跌幅": [2.5, -1.0]})

    result = market_close_review(stocks, sectors, "行业")

    assert result["市场状态"] == "结构分化"
    assert result["上涨家数"] == 3
    assert result["涨停附近"] == 1
    assert result["跌停附近"] == 1
    assert result["领涨行业"] == "算力"


def test_market_overview_radar_surfaces_breadth_leaders_and_activity():
    import pandas as pd
    from src.calculations import market_overview_radar

    stocks = pd.DataFrame({"涨跌幅": [2.0, 1.0, -1.0, 0.0, 3.0]})
    sectors = pd.DataFrame({
        "行业": ["算力", "银行", "医药"],
        "涨跌幅": [2.8, -1.2, 0.5],
        "成交额": [800, 1200, 500],
    })

    result = market_overview_radar(stocks, sectors, "行业")

    assert result["上涨占比"] == pytest.approx(0.6)
    assert result["广度状态"] == "广度扩散"
    assert result["领涨行业"] == "算力"
    assert result["领跌行业"] == "银行"
    assert result["活跃行业"] == "银行"


def test_decision_alerts_are_non_trading_warnings():
    from src.calculations import decision_alerts
    alerts = decision_alerts(900, 1000, {"total_low": 400, "total_high": 700}, {"unprotected_positions": 1}, None)
    assert "总仓位高于当前阶段参考上限" in alerts
    assert "有 1 只持仓未填写单票止损线" in alerts


def test_market_research_queue_covers_strength_activity_and_divergence():
    from src.calculations import market_research_queue
    frame = pd.DataFrame(
        {
            "行业": ["算力", "银行", "消费"],
            "涨跌幅": [3.0, -2.0, 0.5],
            "上涨占比": [0.9, 0.2, 0.55],
            "成交额": [80.0, 130.0, 60.0],
            "行业强度": [92.0, 20.0, 55.0],
        }
    )

    result = market_research_queue(frame, "行业")

    assert set(result["研究角度"]) == {"强度领先", "规模活跃", "相对市场偏离"}
    assert result.loc[result["研究角度"].eq("强度领先"), "行业"].iloc[0] == "算力"
    assert result.loc[result["研究角度"].eq("规模活跃"), "行业"].iloc[0] == "银行"
    assert result.loc[result["研究角度"].eq("相对市场偏离"), "相对市场"].iloc[0] == -2.5


def test_market_activity_concentration_reports_turnover_structure():
    from src.calculations import market_activity_concentration
    frame = pd.DataFrame({"成交额": [100.0, 50.0, 25.0, 25.0]})

    result = market_activity_concentration(frame, top_n=2)

    assert result["有效样本"] == 4
    assert result["总成交额"] == 200.0
    assert result["前N成交占比"] == 0.75
    assert result["N"] == 2


def test_market_snapshot_trend_summarizes_each_saved_trade_day():
    from src.calculations import market_snapshot_trend
    history = pd.DataFrame({
        "快照日期": ["2026-09-24", "2026-09-24", "2026-09-25", "2026-09-25"],
        "涨跌幅": [1.0, -1.0, 2.0, 1.0],
        "成交额": [100.0, 300.0, 200.0, 200.0],
    })

    result = market_snapshot_trend(history)

    assert result["交易日"].tolist() == ["2026-09-24", "2026-09-25"]
    assert result["上涨占比"].tolist() == [0.5, 1.0]
    assert result["成交额"].tolist() == [400.0, 400.0]
    assert result["涨停附近"].tolist() == [0, 0]
    assert result["跌停附近"].tolist() == [0, 0]


def test_market_snapshot_trend_does_not_include_future_replay_days():
    from src.calculations import market_snapshot_trend

    history = pd.DataFrame({
        "快照日期": ["2026-09-24", "2026-09-25", "2026-09-26"],
        "涨跌幅": [-2.0, 1.0, 9.9],
        "成交额": [100.0, 200.0, 300.0],
    })

    result = market_snapshot_trend(history, through_date="2026-09-25")

    assert result["交易日"].tolist() == ["2026-09-24", "2026-09-25"]
    assert result["上涨占比"].tolist() == [0.0, 1.0]
    assert result["成交额"].tolist() == [100.0, 200.0]


def test_market_snapshot_trend_counts_limit_like_moves():
    from src.calculations import market_snapshot_trend

    history = pd.DataFrame({
        "快照日期": ["2026-09-24", "2026-09-24", "2026-09-25", "2026-09-25"],
        "涨跌幅": [9.9, -9.9, 10.0, 0.0],
    })

    result = market_snapshot_trend(history)

    assert result["涨停附近"].tolist() == [1, 1]
    assert result["跌停附近"].tolist() == [1, 0]


def test_market_snapshot_trend_keeps_unreported_turnover_unknown():
    from src.calculations import market_snapshot_trend, market_trend_summary

    history = pd.DataFrame({
        "快照日期": ["2026-09-24", "2026-09-25", "2026-09-25"],
        "涨跌幅": [1.0, -1.0, 2.0],
        "成交额": [None, "100", None],
    })

    result = market_snapshot_trend(history)

    assert pd.isna(result.loc[0, "成交额"])
    assert result.loc[1, "成交额"] == 100.0
    assert result["成交额有效数"].tolist() == [0, 1]
    assert market_trend_summary(result)["平均成交额"] == 100.0


def test_market_overview_distribution_counts_flat_stocks_separately():
    from src.calculations import market_overview_distribution

    frame = pd.DataFrame({"涨跌幅": [-6.0, -3.0, -0.1, 0.0, 0.1, 3.0, 6.0, None]})
    result = market_overview_distribution(frame)

    assert result["区间"].tolist() == ["<-5%", "-5%~-2%", "-2%~0%", "0%", "0%~2%", "2%~5%", ">5%"]
    assert result["家数"].tolist() == [1, 1, 1, 1, 1, 1, 1]


def test_market_close_temperature_labels_breadth_and_limit_activity():
    from src.calculations import market_close_temperature

    assert market_close_temperature({"上涨占比": 0.78, "涨停附近": 55, "跌停附近": 2})["状态"] == "情绪活跃"
    assert market_close_temperature({"上涨占比": 0.24, "涨停附近": 1, "跌停附近": 40})["状态"] == "情绪低迷"


def test_market_history_coverage_describes_saved_trade_day_range():
    from src.calculations import market_history_coverage

    trend = pd.DataFrame({"交易日": ["2026-09-23", "2026-09-24", "2026-09-25"]})

    assert market_history_coverage(trend) == {"交易日数": 3, "起始日": "2026-09-23", "截至日": "2026-09-25"}


def test_market_trend_summary_returns_breadth_extremes_and_turnover_average():
    from src.calculations import market_trend_summary

    trend = pd.DataFrame({"交易日": ["2026-09-23", "2026-09-24", "2026-09-25"], "上涨占比": [0.3, 0.8, 0.5], "成交额": [100.0, 200.0, 300.0]})

    assert market_trend_summary(trend)["最高广度"] == 0.8
    assert market_trend_summary(trend)["平均成交额"] == 200.0


def test_market_change_distribution_groups_market_breadth_by_return_band():
    from src.calculations import market_change_distribution

    frame = pd.DataFrame({"涨跌幅": [-12.0, -7.0, -2.0, 0.0, 2.0, 7.0, 12.0]})

    result = market_change_distribution(frame)

    assert result["区间"].tolist() == ["<-7%", "-7%~-3%", "-3%~0%", "0%", "0%~3%", "3%~7%", ">7%"]
    assert result["数量"].tolist() == [1, 1, 1, 1, 1, 1, 1]
