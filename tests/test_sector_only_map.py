import json
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_cloud_defaults_to_sector_tiles_instead_of_thousands_of_stock_tiles():
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py')
    app.session_state['active_nav'] = '大盘云图'
    app.run(timeout=30)
    assert not app.exception
    assert app.segmented_control(key='terminal_map_detail').value == '板块'
    tree = next(json.loads(item.proto.spec) for item in app.get('plotly_chart') if json.loads(item.proto.spec)['data'][0]['type']=='treemap')
    assert len(tree['data'][0]['labels']) < 200
    app.segmented_control(key='terminal_map_detail').set_value('个股').run(timeout=30)
    tree = next(json.loads(item.proto.spec) for item in app.get('plotly_chart') if json.loads(item.proto.spec)['data'][0]['type']=='treemap')
    assert len(tree['data'][0]['labels']) > 1000
