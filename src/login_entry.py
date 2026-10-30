"""Login presentation: preview by default, native OIDC callback when configured."""

from collections.abc import Callable
import streamlit as st


def login_preview_requested(params) -> bool:
    return params.get('view') == 'login'


STYLE = '''<style>
.stApp {background:radial-gradient(ellipse at 18% 36%,#103042 0%,transparent 45%),
 radial-gradient(ellipse at 88% 18%,#10234b 0%,transparent 40%),#070d18 !important;}
[data-testid="stSidebar"] {display:none;}
.block-container {max-width:1280px !important;padding-top:4vh !important;}
.login-brand {display:flex;align-items:center;gap:14px;margin-bottom:62px;}
.login-logo {width:42px;height:42px;border:1px solid #45d5dd;border-radius:12px;
 display:grid;place-items:center;color:#61e8e9;font-size:25px;background:#122b3a;}
.login-brand strong {font-size:21px;letter-spacing:1px;}
.login-brand small {display:block;color:#7c94ae;letter-spacing:3px;font-size:10px;margin-top:5px;}
.login-hero {padding:22px 36px 24px 0;}
.login-eyebrow {color:#d8b86b !important;font-size:12px;letter-spacing:3px;}
.login-hero h1 {font-size:clamp(32px,4vw,58px) !important;line-height:1.26;letter-spacing:2px;margin:22px 0;}
.login-hero h1 span {color:#64dbe5;}
.login-description {color:#9fb2c9 !important;font-size:16px;line-height:1.9;max-width:440px;}
.login-visual {position:relative;margin-top:30px;border:1px solid #244358;border-radius:20px;
 background:linear-gradient(120deg,#11233380,#0c152a80);overflow:hidden;}
.login-visual svg {display:block;width:100%;height:auto;}
.login-visual-label {position:absolute;top:18px;left:22px;font-size:10px;letter-spacing:3px;color:#698ca6;}
.login-visual-foot {display:flex;justify-content:space-between;padding:0 22px 17px;color:#7895ac;font-size:11px;}
.st-key-login_card {padding:30px !important;border:1px solid #34536e !important;border-radius:22px !important;
 background:linear-gradient(145deg,#15243bf0,#0d192bef) !important;box-shadow:0 22px 70px #00000040;}
.st-key-login_card h2 {font-size:27px !important;}
.st-key-login_card button {min-height:42px;}
.st-key-login_card [data-testid="stButton"] button[kind="primary"] {background:#16798b;border-color:#329cac;color:#d1ecf0;}
.st-key-login_card [data-testid="stTextInput"] {margin-top:8px;}
.login-footer {margin-top:42px;padding:22px 0;border-top:1px solid #20354b;color:#7890a9;
 font-size:12px;display:flex;gap:16px;flex-wrap:wrap;justify-content:space-between;}
@media(max-width:700px){.login-brand{margin-bottom:20px}.login-hero{padding-right:0}
 .login-visual{margin-bottom:20px}.st-key-login_card{padding:20px !important}.block-container{padding-top:20px !important;}}
</style>'''

HERO = '''<section class="login-hero">
<div class="login-eyebrow">FINANCE × TECHNOLOGY</div>
<h1>您的专属<br><span>复盘工具</span></h1>
<p class="login-description">看清市场，梳理持仓，<br>让每一次交易都有迹可循。</p>
<div class="login-visual">
<div class="login-visual-label">MARKET INTELLIGENCE / 示意视觉 · 非行情</div>
<svg viewBox="0 0 600 225" role="img" aria-label="金融科技抽象走势示意图，非真实行情">
<defs><pattern id="login-grid" width="40" height="40" patternUnits="userSpaceOnUse">
<path d="M40 0H0V40" fill="none" stroke="#254557" stroke-width=".6"/></pattern>
<linearGradient id="login-area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#37dce2" stop-opacity=".25"/>
<stop offset="1" stop-color="#37dce2" stop-opacity="0"/></linearGradient></defs>
<rect width="600" height="225" fill="url(#login-grid)"/>
<path d="M0 176L48 161L86 175L128 133L167 146L204 116L250 138L292 91L335 110L377 83L423 97L466 52L510 71L555 47L600 58V225H0Z" fill="url(#login-area)"/>
<path d="M0 176L48 161L86 175L128 133L167 146L204 116L250 138L292 91L335 110L377 83L423 97L466 52L510 71L555 47L600 58" fill="none" stroke="#57dce7" stroke-width="2.5"/>
<path d="M0 191Q155 188 240 160T430 134T600 99" fill="none" stroke="#c4a65a" stroke-width="1.5" stroke-dasharray="5 6"/>
<circle cx="466" cy="52" r="6" fill="#d8bc75" stroke="#faf0c5"/>
</svg><div class="login-visual-foot"><span>全局视角</span><span>数据驱动</span><span>独立研究</span></div>
</div></section>'''


def render_login_entry(on_login: Callable[[], None] | None = None) -> None:
    st.html(STYLE)
    st.html('''<div class="login-brand"><div class="login-logo">⌁</div>
    <div><strong>TradingAgents</strong><small>A-SHARE RESEARCH WORKSPACE</small></div></div>''')
    brand, login = st.columns([1.35, 1], gap='large')
    with brand:
        st.html(HERO)
    with login.container(border=True, key='login_card'):
        st.badge('邀请制体验', icon=':material/verified_user:', color='blue')
        st.header('欢迎进入研究工作台')
        st.caption('一个账号，连接市场洞察与个人研究。')
        if on_login is not None:
            st.caption('使用受邀用户名和密码登录。首次登录需设置自己的密码。')
            st.button('账号密码登录', type='primary', on_click=on_login,
                      key='guest_signin', width='stretch')
            st.caption('密码仅在身份服务页面输入；当前暂不提供短信登录。')
        else:
            render_preview_fields()
        with st.expander('没有账号？邀请注册', icon=':material/person_add:'):
            st.caption('仅限受邀朋友。请联系管理员开通账号，首次登录修改临时密码；忘记密码请联系管理员重置。')
        with st.expander('隐私与使用说明', icon=':material/privacy_tip:'):
            if on_login is None:
                st.caption('当前为外观预览，不提供认证或数据隔离，不收集注册资料。')
            else:
                st.caption('身份服务验证账号，网站按邀请权限开放研究页面。用户名登录不等于实名认证。')
            st.caption('工具仅供研究参考，不构成投资建议，不保证收益。')
    st.html('''<footer class="login-footer"><span>TradingAgents · 洞察市场，研究先行</span>
    <span>研究参考 · 非投资建议</span></footer>''')


def render_preview_fields() -> None:
        mode = st.segmented_control('登录方式', ['账号密码', '手机验证码'],
            default='账号密码', required=True, key='login_preview_mode', width='stretch',
            label_visibility='collapsed')
        if mode == '账号密码':
            st.text_input('用户名', placeholder='请输入用户名', disabled=True, key='preview_username')
            st.text_input('密码', type='password', placeholder='请输入密码', disabled=True, key='preview_password')
        else:
            st.text_input('手机号', placeholder='请输入已验证的手机号', disabled=True, key='preview_phone')
            st.text_input('短信验证码', placeholder='请输入验证码', disabled=True, key='preview_code')
            st.button('获取验证码', disabled=True, key='preview_send_sms', width='stretch')
        st.button('进入工作台', type='primary', disabled=True, key='preview_signin', width='stretch')
        st.warning('预览：认证服务尚未配置。暂不接收账号、密码或手机号。', icon=':material/info:')
