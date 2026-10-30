"""Market activity with explicit snapshot coverage and volume units."""
import pandas as pd
import streamlit as st
import numpy as np


from .public_workspace.report_model import activity_totals,activity_comparison


def render_market_activity(data):
    from .closing_report import owner_overview_panels
    return owner_overview_panels(data).render_market_activity(data)
