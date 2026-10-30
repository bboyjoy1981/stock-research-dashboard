"""Common display boundaries; no loading or personal-source fallback."""
import pandas as pd
import streamlit as st
from .contracts import PublicCapabilities


def public_table(frame,fields,capabilities,**kwargs):
    """Transmit only the caller's audited fields, never a source index."""
    if not isinstance(frame,pd.DataFrame) or frame.columns.duplicated().any():
        raise ValueError('Invalid public display table')
    if not isinstance(capabilities,PublicCapabilities):
        raise ValueError('Explicit public capabilities required')
    public=frame[[field for field in dict.fromkeys(fields) if field in frame]].copy(deep=True).reset_index(drop=True)
    if any(not pd.api.types.is_scalar(value) for value in public.to_numpy().flat):
        raise ValueError('Public display cells must be scalar')
    if capabilities.download:
        return st.dataframe(public,**kwargs)
    # Static guest tables do not expose the interactive dataframe export toolbar.
    options={key:value for key,value in kwargs.items() if key in ('width','height','hide_index','border')}
    return st.table(public,**options)
