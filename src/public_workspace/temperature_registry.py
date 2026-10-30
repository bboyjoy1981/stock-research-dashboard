"""Existing source registry, not a claim of complete/current collection."""
RELEASES = (
    dict(indicator_id='cn_pmi', name='中国制造业PMI',
         url='https://www.stats.gov.cn/zwfwck/sjfb/202609/t20260930_1965449.html',
         published='2026-09-30T09:30:00+08:00', period='2026-09',
         valid_until='2026-10-31T09:30:00+08:00'),
    dict(indicator_id='cn_cpi_yoy', name='中国CPI同比',
         url='https://www.stats.gov.cn/sj/zxfbhjd/202610/t20261014_1965477.html',
         published='2026-10-14T09:30:00+08:00', period='2026-09',
         valid_until='2026-11-09T09:30:00+08:00'),
)

PENDING_SOURCES = (
    ('美国PMI原始发布版本', 'https://www.prnewswire.com/news-releases/manufacturing-pmi-at-54-5-september-2026-ism-manufacturing-pmi-report-302894520.html', 'ISM发布的历史报告已接入最近捕获；原始历史发布时间版本尚未补齐，不能回填旧复盘日'),
    ('美国CPI', 'https://www.bls.gov/bls/news-release/cpi.htm', '本机程序访问返回403；不绕过限制，归档接入待完成'),
    ('中国政策利率历史', 'https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html', '最近完整月份已接入7天逆回购公告；更长历史与原始发布版本待补齐'),
    ('美联储政策', 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm', '利率发布版本与月末序列待接入'),
    ('欧洲央行政策', 'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html', '待核验利率口径和历史版本'),
    ('日本央行政策', 'https://www.boj.or.jp/en/mopo/', '待核验政策利率与发布时间'),
    ('沪市两融', 'https://www.sse.com.cn/market/othersdata/margin/sum/', '需沪深同日融资余额和融资买入额，历史尚未接入'),
    ('深市两融', 'https://www.szse.cn/disclosure/index.html', '公开披露入口已找到，数据适配未完成'),
    ('新增开户', 'https://www.chinaclear.cn/', '账户数/投资者数必须区分，固定统计定义尚未确认'),
    ('KOSPI', 'https://data.krx.co.kr/', '本次请求韩国交易所数据接口返回LOGOUT；同日历史尚未接通'),
    ('地缘风险', '', '需来源事件和人工复核；当前待核实，不自动推断无风险'),
)

