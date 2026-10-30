from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_daily_surface_marks_missing_minutes_and_exposes_volume():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py')
    app.session_state['active_nav'] = '个股详情'
    app.run(timeout=30)
    assert not app.exception
    assert '当日走势与量价' in [item.value for item in app.subheader]
    assert '成交量（原始单位）' in [item.label for item in app.metric]
    assert any('尚未接入分钟行情' in item.value for item in app.info)
