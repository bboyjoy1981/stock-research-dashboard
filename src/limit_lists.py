"""Daily close-limit members from the selected snapshot, never threshold estimates."""
import streamlit as st
from .price_limits import confirmed_limit_rows
from .ui import _open_recent_stock


def render_limit_lists(stocks,date,snapshot=None):
    from .closing_report import owner_overview_panels
    data=dict(stocks=stocks,import_date=date)
    return owner_overview_panels(data).render_limit_lists(stocks,date,snapshot)
