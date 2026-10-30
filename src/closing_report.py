"""Downloadable factual recap of the selected market snapshot, not a signal."""
import pandas as pd
import streamlit as st


from .public_workspace.report_model import closing_report


def owner_overview_panels(data):
    """Owner entry adapter; only this side reads local public-news storage."""
    from datetime import datetime,timezone
    from .public_workspace.pages.overview_panels import OverviewPanels
    from .public_workspace.contracts import PublicCapabilities
    from .core_workspace import owner_cloud_navigation
    from .news_snapshot import load_news_state
    from .public_workspace.news_model import news_dataset,decode_news_dataset
    prepared=dict(data)
    try:
        state=load_news_state()
        dataset=news_dataset(state,set(),datetime.now(timezone.utc).isoformat())
        prepared['public_news_state']=decode_news_dataset(dataset,datetime.now(timezone.utc))
    except (OSError,ValueError,KeyError,TypeError):
        prepared['public_news_state']=None
    return OverviewPanels(prepared,PublicCapabilities(download=True),owner_cloud_navigation())

def render_closing_report(data,sectors,field):
    return owner_overview_panels(data).render_closing_report(data,sectors,field)
