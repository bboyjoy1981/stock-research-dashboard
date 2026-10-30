"""Owner compatibility entry; shared classification/rendering live elsewhere."""
import pandas as pd
import streamlit as st
from .public_workspace.classification import (
    prepare_stocks,industry_members,theme_members,THEMES,CHECKED_ON,_number,
)


def render_sector_directory(data):
    from .public_workspace.navigation import PublicNavigation
    from .public_workspace.pages.sector_directory import render_frame

    class OwnerDirectoryNavigation(PublicNavigation):
        def open_stock(self,code,allowed_codes,industry=None,parent=None):
            if not super().open_stock(code,allowed_codes,industry,parent):
                return False
            from .ui import _clear_research_path
            _clear_research_path()
            self.state['stock_detail_query']=code
            self.state.pop('stock_detail_selection',None)
            self.state['active_nav']='个股详情'
            return True

    source='imported' if data.get('stock_quote_source')=='imported' else '演示 / 测试数据；不代表真实市场行情。'
    render_frame(data.get('stocks',pd.DataFrame()),data.get('import_date'),source,
        OwnerDirectoryNavigation('owner',('板块细分','个股详情','大盘云图'),st.session_state))
