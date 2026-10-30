from streamlit.testing.v1 import AppTest


def test_login_entry_is_honest_preview_and_switches_modes(monkeypatch):
    import requests
    def forbidden(*args, **kwargs):
        raise AssertionError('Preview must not send network requests')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    at = AppTest.from_string('from src.login_entry import render_login_entry\nrender_login_entry()').run()
    assert not at.exception
    assert any('认证服务尚未配置' in item.value for item in at.warning)
    assert len(at.text_input) == 2
    assert all(item.disabled for item in at.text_input)
    assert at.button[0].disabled
    at.segmented_control[0].set_value('手机验证码').run()
    assert not at.exception
    assert [item.label for item in at.text_input] == ['手机号', '短信验证码']
    assert all(item.disabled for item in at.text_input)
    assert all(item.disabled for item in at.button)
    assert any('邀请注册' in item.label for item in at.status)
    assert not at.success


def test_preview_route_skips_business_loaders(monkeypatch):
    import src.demo_data
    def forbidden():
        raise AssertionError('Login preview must not load market data')
    monkeypatch.setattr(src.demo_data, 'load_demo_market', forbidden)
    at = AppTest.from_file('../app.py')
    at.query_params['view'] = 'login'
    at.run()
    assert not at.exception
    assert any('认证服务尚未配置' in item.value for item in at.warning)
    assert not at.sidebar.radio


def test_login_preview_route_is_explicit():
    from src.login_entry import login_preview_requested
    assert login_preview_requested({'view': 'login'})
    for params in ({}, {'view': 'market'}, {'view': 'LOGIN'}):
        assert not login_preview_requested(params)
