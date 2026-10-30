"""Owner compatibility entry for the shared snapshot candidate workbench."""
import pandas as pd
import streamlit as st
from .public_workspace.scanner_model import (
    filter_candidates,candidate_review_report,quote_detail_values,_number,_display,
)


def render_candidate_workspace(data):
    from .public_workspace.pages.scanner import render_frame
    from .public_workspace.contracts import PublicCapabilities
    from .public_workspace.navigation import PublicNavigation
    class OwnerScannerNavigation(PublicNavigation):
        def open_stock(self,code,allowed_codes,industry=None,parent=None):
            if not super().open_stock(code,allowed_codes,industry,parent): return False
            self.state["stock_detail_query"]=code
            self.state.pop("stock_detail_selection",None)
            self.state["research_context"]={"source":"候选股扫描","industry":industry or ""}
            self.state["active_nav"]="个股详情"
            return True
        def focus_sector(self,field,value,allowed_pairs,parent=None):
            if not super().focus_sector(field,value,allowed_pairs,parent): return False
            self.state["terminal_industry_query"]=value
            self.state["terminal_level"]=field
            self.state["research_context"]={"source":"候选股扫描","industry":value}
            self.state["active_nav"]="大盘云图"
            return True
    render_frame(data,PublicCapabilities(download=True),
        OwnerScannerNavigation("owner",("盘中选股","大盘云图","个股详情"),st.session_state))
