import pandas as pd
import streamlit as st
from .snapshot_review import compare_saved_snapshots, snapshot_change_distribution, industry_snapshot_comparison


def reset_review_filters():
    for key in ("overview_compare_search", "overview_compare_movement", "overview_compare_industry", "overview_compare_sort", "overview_compare_direction", "overview_compare_stock", "overview_compare_page"):
        st.session_state.pop(key, None)


def render_market_snapshot_comparison(data):
    from .closing_report import owner_overview_panels
    return owner_overview_panels(data).render_market_snapshot_comparison(data)


def render_industry_comparison_board(board,current_date,baseline,components=None,expanded=False):
    from .closing_report import owner_overview_panels
    return owner_overview_panels(dict(stocks=components)).render_industry_comparison_board(board,current_date,baseline,components,expanded)


def render_stock_snapshot_comparison(history, code):
    from .public_workspace.pages.stock_comparison import render
    from .public_workspace.contracts import PublicCapabilities
    return render(history,code,PublicCapabilities(download=True))
