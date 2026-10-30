"""Exact-sector research surface shared by snapshot market pages."""
import pandas as pd
import streamlit as st
from .core_workspace import open_core_stock, open_full_cloud, quote_export


def sector_recap(members):
    from .public_workspace.cloud_model import sector_recap as shared
    return shared(members)


def render_sector_recap(members):
    from .public_workspace.pages.cloud_components import render_sector_recap as shared
    return shared(members)


def sector_snapshot(stocks,field,selected):
    from .public_workspace.cloud_model import sector_snapshot as shared
    return shared(stocks,field,selected)


def open_sector_cloud(field, selected, parent=None):
    open_full_cloud()
    st.session_state['terminal_level'] = field
    st.session_state['core_cloud_group'] = selected
    if parent:
        st.session_state['core_cloud_parent'] = parent
    st.session_state['terminal_minimum'] = 1
    st.session_state['terminal_include_unclassified'] = True
    if selected not in {'未分类', '未细分'}:
        st.session_state['research_context'] = {'source': '行业研究台', 'industry': selected}


def render_sector_lens(stocks,field,data,prefix):
    from .public_workspace.pages.cloud_components import render_sector_lens as shared
    from .public_workspace.contracts import PublicCapabilities
    from .core_workspace import owner_cloud_navigation
    return shared(stocks,field,data,prefix,PublicCapabilities(download=True),owner_cloud_navigation(),session_prefix='')
