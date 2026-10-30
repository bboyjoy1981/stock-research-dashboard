"""PCB panorama transcribed from the user's reference, not a live constituent feed."""
import pandas as pd
import streamlit as st

from .public_workspace.reference_model import (GROUPS,reference_quotes,filter_reference_quotes,
    _change_style,reference_summary,reference_export)


def _reset_reference_filters():
    st.session_state.update({"pcb_reference_query": "", "pcb_reference_layer": "全部分层",
                             "pcb_reference_sort": "参考顺序", "pcb_reference_matched": False})


def _open_member(code):
    st.session_state["stock_detail_query"] = code
    st.session_state.pop("stock_detail_selection", None)
    st.session_state["active_nav"] = "个股详情"


def render_reference_chain(data):
    from .public_workspace.pages.industry_chain import render_reference_frame
    from .public_workspace.contracts import PublicCapabilities
    render_reference_frame(data.get('stocks',pd.DataFrame()),data.get('import_date'),
        PublicCapabilities(download=True),owner_chain_navigation())


def owner_chain_navigation():
    from .public_workspace.navigation import PublicNavigation
    class OwnerChainNavigation(PublicNavigation):
        def open_stock(self,code,allowed_codes,industry=None,parent=None):
            if not super().open_stock(code,allowed_codes,industry,parent):
                return False
            _open_member(code)
            return True
    return OwnerChainNavigation('owner',('产业链分层','个股详情'),st.session_state)
