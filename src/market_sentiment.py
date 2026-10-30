"""Public-web market-topic and sentiment research views.

The first snapshot is a small, source-linked web sample. It is not a live
social-media crawl and intentionally does not infer crowd sentiment from
market performance or article headlines.
"""

import html
import json
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from src.news_snapshot import load_news_state, latest_changed_ids
from src.social_hot import recent_posts


SAMPLE_TRADE_DATE = "2026-10-09"
SAMPLE_CAPTURE_DATE = "2026-10-11"
CAPTURED_AT = "2026-10-11 16:23（北京时间）"

# One-time public-web capture for demonstration. Source dates are kept separate
# from the capture timestamp; media opinions are not treated as official facts.
CAPTURED_UPDATES = {
    "政策监管": [
        {
            "标题": "证监会召开资本市场和金融形势专家座谈会",
            "日期": "2026-10-10",
            "标签": "监管动态 · 座谈会建议",
            "摘要": "与会者建议加强稳市机制、拓宽中长期资金入市渠道、推动分红回购、优化发行上市制度并强化交易和跨境风险监测。",
            "口径": "这是听取意见建议的座谈会，不代表相关措施已经出台或生效。",
            "来源": "中国证监会",
            "链接": "https://www.csrc.gov.cn/csrc/c100028/c7663814/content.shtml",
        },
        {
            "标题": "中共中央、国务院印发《关于发展新质生产力的意见》",
            "日期": "2026-10-09",
            "标签": "政策文件 · 已公开发布",
            "摘要": "文件提出以科技创新为引领，推进关键核心技术攻关、企业科技创新、科技成果转化，以及科技创新和产业创新融合。",
            "口径": "政策方向覆盖面广，落到具体行业和上市公司仍需核对后续配套政策、订单与业绩。",
            "来源": "工业和信息化部转载新华社全文",
            "链接": "https://www.miit.gov.cn/xwfb/szyw/art/2026/art_bb063b402f814c2d829cb53688ee84c0.html",
        },
    ],
    "公司公告": [
        {
            "标题": "广电网络：法院决定受理预重整并指定临时管理人",
            "日期": "2026-10-10",
            "标签": "600831 · 风险事件",
            "摘要": "上交所公告列表显示公司披露被债权人申请预重整、法院决定受理预重整、招募重整投资人等公告。",
            "口径": "预重整不等于法院已正式受理重整；后续结果和风险警示状态需以法院及公司公告为准。",
            "来源": "上海证券交易所",
            "链接": "https://www.sse.com.cn/disclosure/listedinfo/announcement/index.shtml?productId=688688",
        },
        {
            "标题": "唐山港披露 2026 年 1—9 月主要生产数据",
            "日期": "2026-10-10",
            "标签": "601000 · 经营数据",
            "摘要": "公司自愿披露前三季度主要生产数据；公告摘要显示货物吞吐量约 1.89 亿吨、同比增长 5.06%。",
            "口径": "生产数据是经营指标，不等同于收入或利润；以公司公告及后续定期报告为准。",
            "来源": "上海证券交易所",
            "链接": "https://www.sse.com.cn/assortment/stock/list/info/announcement/index.shtml?productId=601000",
        },
    ],
    "宏观日历": [
        {
            "标题": "中国 9 月 CPI、PPI",
            "日期": "2026-10-14 09:30",
            "标签": "国家统计局 · 计划发布时间",
            "摘要": "国家统计局 2026 年常规发布日程列示，10 月 14 日 9:30 发布 CPI 与工业生产者出厂价格指数（PPI）。",
            "口径": "这是预定发布时间；实际发布可能调整，发布后再补实际值、前值和市场预期。",
            "来源": "国家统计局 2026 年发布日程",
            "链接": "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/202512/t20251226_1962154.html",
        },
        {
            "标题": "国民经济运行情况及多项月度数据",
            "日期": "2026-10-19 10:00",
            "标签": "国家统计局 · 计划发布时间",
            "摘要": "日程安排包括国民经济运行情况，以及规模以上工业、能源、固定资产投资等月度数据。",
            "口径": "以国家统计局后续实际发布为准；房价指数等分项在日程中另有发布时间。",
            "来源": "国家统计局 2026 年发布日程",
            "链接": "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/202512/t20251226_1962154.html",
        },
    ],
}

CAPTURED_NEWS = [
    {
        "标题": "券商资管四季度最新策略：多家受访机构股票配置优先级靠前",
        "日期": "2026-10-11 09:25",
        "标签": "机构观点 · 媒体报道",
        "摘要": "报道汇总多家券商资管看法，多数受访机构把股票配置排在商品和债券之前；对债券和商品的排序仍有分歧。",
        "口径": "这是媒体采访中的机构观点，不是监管结论、全市场共识或收益保证。",
        "来源": "券商中国 / 东方财富",
        "链接": "https://finance.eastmoney.com/a/202610113892023587.html",
        "关联主题": "大类资产配置、成长与红利",
    },
    {
        "标题": "证监会资本市场和金融形势专家座谈会",
        "日期": "2026-10-10",
        "标签": "政策线索 · 官方原文",
        "摘要": "会议公开了与会专家关于稳市机制、中长期资金、分红回购和风险监测等方面的建议。",
        "口径": "座谈会建议不等同于已出台政策，具体措施需等待正式文件。",
        "来源": "中国证监会",
        "链接": "https://www.csrc.gov.cn/csrc/c100028/c7663814/content.shtml",
        "关联主题": "资本市场制度、长期资金",
    },
]

CAPTURED_MARKET_HEAT = [
    {
        "标题": "最近交易日收盘复盘：指数探底回升，传媒方向活跃",
        "日期": "2026-10-09 收盘",
        "标签": "最近交易日 · 媒体复盘",
        "摘要": "财联社复盘提到三大指数探底回升、两市成交额约 1.9 万亿元，影视传媒等方向午后表现活跃。",
        "口径": "这是 10 月 9 日收盘复盘；当前是周日，没有 A 股盘中交易数据。板块表现不代表后续走势。",
        "来源": "财联社",
        "链接": "https://www.cls.cn/detail/2500549",
    },
    {
        "标题": "周末机构配置讨论：股票排序靠前，但机构判断存在分歧",
        "日期": "2026-10-11",
        "标签": "周末关注 · 机构观点",
        "摘要": "媒体采访中的多家资管机构谈到四季度大类资产配置；报道同时呈现对债券、商品及权益风险的不同判断。",
        "口径": "仅代表受访机构观点，不能当作社交平台热度排名或个股推荐。",
        "来源": "券商中国 / 东方财富",
        "链接": "https://finance.eastmoney.com/a/202610113892023587.html",
    },
]

TOPICS = [
    {
        "主题": "短剧游戏 / 文化传媒",
        "信号": "收盘复盘中相关个股较集中，传媒与影视方向表现活跃",
        "代表个股": "中文在线、芒果超媒、新华传媒、文投控股",
        "依据": "公开涨停复盘与收盘综述",
        "来源": "打板客网",
        "链接": "https://www.dabanke.com/?_canonical_recover=20260920",
    },
    {
        "主题": "电池 / 固态电池 / 储能",
        "信号": "多只电池相关股票出现在公开人气榜或涨停复盘中",
        "代表个股": "龙蟠科技、时代万恒、传艺科技、上海洗霸、雄韬股份",
        "依据": "人气榜提及与题材复盘；不代表题材业务已形成收入",
        "来源": "金融界、打板客网",
        "链接": "https://stock.jrj.com.cn/2026/10/09091858637741.shtml",
    },
    {
        "主题": "贵金属",
        "信号": "10 月 9 日行业复盘列为涨幅靠前方向",
        "代表个股": "西部黄金",
        "依据": "公开收盘复盘；板块表现不等于社媒情绪",
        "来源": "同花顺财经",
        "链接": "https://news.10jqka.com.cn/20261009/c680520275.shtml",
    },
]

HOT_STOCKS = [
    {"榜单顺位": 1, "股票": "江淮汽车", "热度依据": "公开人气热股榜提及", "相关方向": "汽车", "来源": "金融界"},
    {"榜单顺位": 2, "股票": "龙蟠科技", "热度依据": "公开人气热股榜提及", "相关方向": "电池 / 固态电池", "来源": "金融界"},
    {"榜单顺位": 3, "股票": "新华传媒", "热度依据": "公开人气热股榜提及", "相关方向": "文化传媒 / 出版", "来源": "金融界"},
    {"榜单顺位": 4, "股票": "时代万恒", "热度依据": "公开人气热股榜提及", "相关方向": "电池 / 储能", "来源": "金融界"},
    {"榜单顺位": 5, "股票": "传艺科技", "热度依据": "公开人气热股榜提及", "相关方向": "电池 / 固态电池", "来源": "金融界"},
    {"榜单顺位": 6, "股票": "上海洗霸", "热度依据": "公开人气热股榜提及", "相关方向": "固态电池 / 液冷", "来源": "金融界"},
    {"榜单顺位": 7, "股票": "圣阳股份", "热度依据": "公开人气热股榜提及", "相关方向": "电池 / 储能", "来源": "金融界"},
    {"榜单顺位": 8, "股票": "雄韬股份", "热度依据": "公开人气热股榜提及", "相关方向": "电池 / 数据中心备用电源", "来源": "金融界"},
    {"榜单顺位": 9, "股票": "九阳股份", "热度依据": "公开人气热股榜提及", "相关方向": "机器人 / 消费", "来源": "金融界"},
    {"榜单顺位": 10, "股票": "金牛化工", "热度依据": "公开人气热股榜提及", "相关方向": "化工", "来源": "金融界"},
]

NEWS = [
    {
        "分类": "市场复盘",
        "标题": "A 股每日行情复盘（10 月 9 日）",
        "摘要": "主要指数小幅收涨；影视院线、文化传媒和贵金属方向涨幅靠前。",
        "来源": "同花顺财经",
        "日期": SAMPLE_TRADE_DATE,
        "链接": "https://news.10jqka.com.cn/20261009/c680520275.shtml",
        "关联主题": "文化传媒、贵金属",
    },
    {
        "分类": "人气榜单",
        "标题": "10 月 9 日 A 股人气热股榜",
        "摘要": "榜单列出江淮汽车、龙蟠科技、新华传媒、时代万恒等 10 只热股；榜单热度不等于社交平台讨论量。",
        "来源": "金融界",
        "日期": SAMPLE_TRADE_DATE,
        "链接": "https://stock.jrj.com.cn/2026/10/09091858637741.shtml",
        "关联主题": "汽车、电池、文化传媒",
    },
    {
        "分类": "题材复盘",
        "标题": "10 月 9 日涨停复盘：短剧游戏等题材活跃",
        "摘要": "复盘页面统计了当日题材和涨停表现；个股题材标签需要再核实公司公告与实际业务。",
        "来源": "打板客网",
        "日期": SAMPLE_TRADE_DATE,
        "链接": "https://www.dabanke.com/?_canonical_recover=20260920",
        "关联主题": "短剧游戏、AI 应用与文娱",
    },
]

SOURCE_CATEGORIES = {
    "政策监管": {
        "说明": "优先显示正式发布的政策、征求意见稿和监管措施，并标注文件状态。下方是本次手动捕捉的官方样本，后台自动同步尚未接入。",
        "重点监测": "国务院及部委政策、货币与流动性操作、产业政策、资本市场规则、交易所监管动态",
        "来源": [
            {"名称": "国务院政策文件库", "机构": "中国政府网", "链接": "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary"},
            {"名称": "人民银行", "机构": "中国人民银行", "链接": "https://www.pbc.gov.cn/"},
            {"名称": "发展改革委文件库", "机构": "国家发展和改革委员会", "链接": "https://www.ndrc.gov.cn/xxgk/wjk/"},
            {"名称": "证监会", "机构": "中国证券监督管理委员会", "链接": "https://www.csrc.gov.cn/"},
            {"名称": "上交所监管动态", "机构": "上海证券交易所", "链接": "https://www.sse.com.cn/regulation/supervision/dynamic/"},
        ],
    },
    "公司公告": {
        "说明": "公告应以交易所或法定披露平台原文为准。下方是本次手动捕捉的公告样本，后台自动采集和持续公告解读尚未接入。",
        "重点监测": "业绩预告/快报、重大合同、并购重组、回购与股东增减持、质押冻结、诉讼、停复牌、风险提示与监管问询",
        "来源": [
            {"名称": "巨潮资讯网", "机构": "法定信息披露平台", "链接": "https://www.cninfo.com.cn/new/index?lang=zh"},
            {"名称": "上交所最新公告", "机构": "上海证券交易所", "链接": "https://www.sse.com.cn/disclosure/listedinfo/announcement/index.shtml"},
            {"名称": "深交所上市公司公告", "机构": "深圳证券交易所", "链接": "https://www.szse.cn/disclosure/notice/company/index.html"},
        ],
    },
    "宏观日历": {
        "说明": "先关注预定发布时间，数据发布后记录实际值、前值和市场预期。下方为官方日程样本，自动同步日历和发布后填入实际值尚未接入。",
        "重点监测": "GDP、CPI/PPI、PMI、工业增加值、社融与信贷、公开市场操作，以及公司财报预约披露日",
        "来源": [
            {"名称": "主要统计信息发布日程", "机构": "国家统计局", "链接": "https://www.stats.gov.cn/xxgk/sjfb/fbrcb/"},
            {"名称": "人民银行公开市场业务", "机构": "中国人民银行", "链接": "https://www.pbc.gov.cn/"},
            {"名称": "定期报告预约披露", "机构": "上海证券交易所", "链接": "https://www.sse.com.cn/disclosure/listedinfo/periodic/"},
        ],
    },
}

MEDIA_SOURCES = [
    {"名称": "财联社 7×24 电报", "机构": "财经通讯社；媒体线索，需核验", "链接": "https://www.cls.cn/telegraph"},
]


def _open_sentiment_page():
    st.session_state["active_nav"] = "热点舆情"


def _render_captured_cards(items):
    st.subheader(f"本次捕捉到的内容 · {len(items)} 条", icon=":material/radar:")
    st.caption(f"抓取整理时间：{CAPTURED_AT} · 每条保留来源页面日期；这是一次性网页采集样例。")
    for item in items:
        with st.container(border=True):
            st.markdown(f"**{item['标题']}**")
            st.caption(f"{item['日期']}｜{item['来源']}｜{item['标签']}")
            st.write(item["摘要"])
            st.caption(f"口径提示：{item['口径']}")
            st.link_button("查看来源原文", item["链接"], icon=":material/open_in_new:")


def render_market_sentiment_preview(market_date=None):
    from .closing_report import owner_overview_panels
    return owner_overview_panels(dict(import_date=market_date)).render_news_preview(market_date)


def _render_historical_sentiment_page(data):
    """Render source directories and dated market-topic/news samples."""
    st.title("热点舆情")
    st.caption("政策、公司公告、宏观日历、新闻快讯和市场热度分开展示；社交平台情绪需要接入授权数据后再统计。")
    market_date = str(data.get("import_date") or "未提供")
    st.caption(f"行情快照交易日：{market_date} · 网页样本交易日：{SAMPLE_TRADE_DATE} · 整理日期：{SAMPLE_CAPTURE_DATE}")
    if market_date not in {SAMPLE_TRADE_DATE, "未提供"}:
        st.info("网页样本与当前行情快照不是同一交易日，页面仅并列展示，不做同日涨跌归因。")
    st.warning(f"以下是 {CAPTURED_AT} 的一次性公开网页采集结果，不是后台实时推送。媒体观点与官方事实分开标注；未取得社交平台帖子和评论样本，因此不计算看多/看空比例。")

    metric_row = st.container(horizontal=True)
    with metric_row:
        st.metric("热点主题", len(TOPICS), border=True)
        st.metric("榜单个股", len(HOT_STOCKS), border=True)
        st.metric("本次捕捉", sum(len(items) for items in CAPTURED_UPDATES.values()) + len(CAPTURED_NEWS) + len(CAPTURED_MARKET_HEAT), border=True)
        st.metric("自动更新", "未接入", border=True)

    view = st.segmented_control(
        "信息分类",
        ["政策监管", "公司公告", "宏观日历", "新闻快讯", "市场热度"],
        default="政策监管",
        key="historical_market_signal_category",
    ) or "政策监管"

    if view in SOURCE_CATEGORIES:
        category = SOURCE_CATEGORIES[view]
        st.subheader(f"{view}信息源", icon=":material/account_balance:")
        st.caption(category["说明"])
        with st.container(border=True):
            st.markdown("**重点监测**")
            st.write(category["重点监测"])
            st.caption("本次已展示手动捕捉样本 · 后台自动同步：未接入")
        columns = st.columns(2)
        for index, source in enumerate(category["来源"]):
            with columns[index % 2]:
                with st.container(border=True):
                    st.markdown(f"**{source['名称']}**")
                    st.caption(source["机构"])
                    st.link_button("打开官方来源", source["链接"], icon=":material/open_in_new:")
        _render_captured_cards(CAPTURED_UPDATES[view])
    elif view == "新闻快讯":
        st.subheader("财经新闻线索", icon=":material/newspaper:")
        st.caption("媒体适合发现线索；涉及政策和公司事实时，优先回查官方原文。下面是本次采集样本，不是实时快讯流。")
        for source in MEDIA_SOURCES:
            st.link_button(f"打开{source['名称']}", source["链接"], icon=":material/open_in_new:")
        _render_captured_cards(CAPTURED_NEWS)
        st.subheader("较早的市场复盘样本", icon=":material/history:")
        for item in NEWS:
            with st.container(border=True):
                st.markdown(f"**{item['标题']}**")
                st.caption(f"{item['日期']}｜{item['来源']}｜{item['分类']}｜关联：{item['关联主题']}")
                st.write(item["摘要"])
                st.link_button("查看原文", item["链接"], icon=":material/open_in_new:")
    else:
        st.subheader("市场热度与题材", icon=":material/whatshot:")
        st.caption("周末无 A 股盘中行情；本次展示最近交易日复盘和周末机构讨论，不等于社交平台讨论量或投资建议。")
        _render_captured_cards(CAPTURED_MARKET_HEAT)
        st.subheader("此前公开榜单和题材样本", icon=":material/history:")
        stock_tab, topic_tab = st.tabs(["榜单个股", "热点主题"])
        with stock_tab:
            st.caption("顺位只复现来源榜单顺序；未采集社媒提及量，不代表推荐。")
            st.dataframe(pd.DataFrame(HOT_STOCKS), hide_index=True, width="stretch")
            st.link_button(
                "打开金融界原榜单",
                "https://stock.jrj.com.cn/2026/10/09091858637741.shtml",
                icon=":material/open_in_new:",
            )
        with topic_tab:
            st.caption("按公开复盘和榜单中反复出现的题材整理；没有足够社媒样本时只展示市场信号，不贴情绪结论。")
            for topic in TOPICS:
                with st.container(border=True):
                    st.markdown(f"**{topic['主题']}**")
                    st.write(topic["信号"])
                    st.caption(f"代表个股：{topic['代表个股']}｜依据：{topic['依据']}")
                    st.link_button(f"来源：{topic['来源']}", topic["链接"], icon=":material/open_in_new:")

    with st.expander("数据口径与后续接入", expanded=False):
        st.markdown(
            "- **官方源**：政策、公告和宏观日历暂提供官方入口；看板自动采集尚未接入。\n"
            "- **新闻与热度**：现有内容是有日期的媒体复盘和榜单样本，不是实时推送，也不能代表全网讨论。\n"
            "- **舆情方向**：待接入授权的帖子/评论样本后，再按正向、中性、负向及主题归类。\n"
            "- **行情表现**：沿用市场总览快照，和网页热度分开展示；快照非实时。\n"
            "- **核验**：新闻摘要保留原文链接；题材标签和市场观点不等同公司公告或基本面结论。"
        )


def render_market_sentiment_page(data):
    """Read local validated snapshots only; collecting is a separate job."""
    directory = Path(data.get('news_directory', Path(__file__).resolve().parents[1] / 'data/news'))
    state = load_news_state(directory)
    st.title('热点舆情')
    st.caption('公开政策与财经资讯 · 官方事实和媒体报道分开 · 不统计社交平台情绪')
    last = state['last_success_at']
    stamp = datetime.fromisoformat(last).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M') if last else '暂无成功记录'
    successes = sum(row['status']=='success' for row in state['source_results'])
    with st.container(horizontal=True):
        st.metric('最近成功采集', stamp, border=True)
        st.metric('本次新增或修订', state['new_count'], border=True)
        st.metric('有效资讯', len(state['items']), border=True)
        status='本次来源采集成功' if successes and successes==len(state['source_results']) else '部分来源可用' if successes else '暂无有效采集'
        st.metric('采集状态', status, border=True)
    st.caption('采集入口已接通；定时任务独立运行。刷新页面读取新快照，不是盘中实时推送。')
    if not last:
        st.info('暂无有效采集；历史样本不会冒充最新资讯。')
    elif state['stale']:
        st.warning('超过12小时未成功采集，资讯可能过期；保留最后有效结果。')
    for result in state['source_results']:
        if result['status']!='success':
            st.warning(f"{result['category']} · {result['source']}：{result.get('error') or '采集失败'}")
    st.caption(f"行情快照：{data.get('import_date') or '未提供'}；资讯源时间逐条标注，采集时间不等于发布时间，不做同日涨跌归因。")
    view = st.segmented_control('信息分类', ['政策监管','公司公告','宏观日历','新闻快讯','讨论观察'], default='政策监管', key='market_signal_category_v2') or '政策监管'
    if view=='讨论观察':
        st.caption('关注股票的公开讨论，与政策和新闻分开查看。新收录只表示首次进入本地快照，不表示热度高。')
        discussion_view = st.segmented_control('讨论分类', ['浏览较多','最新收录','其他平台'], default='浏览较多', key='discussion_view') or '浏览较多'
        forum_path = Path(__file__).resolve().parents[1] / 'data' / 'forum_hot' / 'latest.json'
        if discussion_view != '其他平台' and forum_path.exists():
            try:
                forum = json.loads(forum_path.read_text(encoding='utf-8'))
                forum_age = datetime.now(ZoneInfo('Asia/Shanghai')) - datetime.fromisoformat(forum['captured_at'])
                if forum_age.total_seconds() < 12 * 3600:
                    checked = len(forum.get('requested_codes', []))
                    succeeded = len(forum.get('succeeded_codes', []))
                    st.caption(f"东方财富股吧 · 采集于 {datetime.fromisoformat(forum['captured_at']):%Y-%m-%d %H:%M} · 关注股票 {succeeded}/{checked} 只采集成功。浏览次数来自股吧列表，不是全网热度。")
                    if forum.get('failed'):
                        st.warning('部分股票采集失败，保留其上次结果：' + '、'.join(row['code'] for row in forum['failed']))
                    stock_options = ['全部股票'] + [next((row['stock'] for row in forum['items'] if row.get('code') == code), code) for code in forum.get('requested_codes', [])]
                    stock_choice = st.selectbox('关注股票', stock_options, key='discussion_stock')
                    selected = [row for row in forum['items'] if stock_choice == '全部股票' or row['stock'] == stock_choice]
                    if discussion_view == '浏览较多':
                        selected = [row for row in selected if isinstance(row.get('views'), int) and row['views'] >= 100]
                        selected.sort(key=lambda row: row['views'], reverse=True)
                        st.caption('只显示本次列表样本中浏览次数至少 100 的帖子，按浏览次数排序；不同发布时间的帖子不宜直接比较。')
                    else:
                        selected = [row for row in selected if row['url'] in forum['new_urls']]
                        selected.sort(key=lambda row: row['updated_at'], reverse=True)
                        st.caption('仅显示本次采集首次进入本地快照的帖子，按股吧列表时间排序；黄色不代表热度高。')
                    if not selected:
                        st.info('此分类暂无符合条件的帖子。')
                    for post in selected[:8]:
                        with st.container(border=True):
                            title = html.escape(post['title'][:110])
                            newly_collected = post['url'] in forum['new_urls']
                            same_day = datetime.fromisoformat(post['updated_at']).date() == datetime.fromisoformat(forum['captured_at']).date()
                            if newly_collected and same_day:
                                st.markdown(f"<strong style='color:#ffd54f'>✦ 今日列表新收录 · {title}</strong>", unsafe_allow_html=True)
                            elif newly_collected:
                                st.markdown(f'**新收录的旧帖 · {title}**')
                            else:
                                st.markdown(f'**{title}**')
                            previous = post.get('code') in {row['code'] for row in forum.get('failed', [])}
                            time_label = '列表发表于' if post.get('time_basis') == '列表发表时间' else '列表更新于'
                            views_label = f" · {post['views']:,} 次浏览" if isinstance(post.get('views'), int) else ' · 浏览数未取得'
                            st.caption(f"{post['stock']} · {time_label} {datetime.fromisoformat(post['updated_at']):%Y-%m-%d %H:%M}{views_label}" + (' · 上次采集快照' if previous else ''))
                            st.link_button('查看原帖', post['url'], icon=':material/open_in_new:')
                    if len(selected) > 8:
                        st.caption(f'当前分类共 {len(selected)} 条，仅展示前 8 条；选择股票可缩小范围。')
                else:
                    st.info('股吧试采快照已超过12小时，等待下次采集。')
            except (OSError, ValueError, KeyError, TypeError):
                st.info('股吧试采快照暂不可用。')
        elif discussion_view == '其他平台':
            crawler_root = Path(__file__).resolve().parents[1] / 'tools' / 'MediaCrawler'
            posts = recent_posts(crawler_root)
            taoguba_path = Path(__file__).resolve().parents[1] / 'data' / 'taoguba_hot' / 'latest.json'
            if taoguba_path.exists():
                try:
                    snapshot = json.loads(taoguba_path.read_text(encoding='utf-8'))
                    if (datetime.now(ZoneInfo('Asia/Shanghai')) - datetime.fromisoformat(snapshot['captured_at'])).total_seconds() < 12 * 3600:
                        posts.extend({'title': row['title'], 'url': row['url'], 'source': row['source'],
                                      'published_at': datetime.fromisoformat(row['published_at']), 'keyword': row['code']}
                                     for row in snapshot['items'])
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            posts.sort(key=lambda row: row['published_at'], reverse=True)
            sources = sorted({post['source'] for post in posts})
            source_choice = st.selectbox('平台来源', ['全部平台', *sources], key='discussion_platform') if sources else '全部平台'
            if source_choice != '全部平台':
                posts = [post for post in posts if post['source'] == source_choice]
            st.caption('淘股吧只收主帖，百度贴吧只收可核对的帖子；均限近 48 小时。按时间排序，不代表跨平台热度排名。')
            if posts:
                for post in posts[:8]:
                    with st.container(border=True):
                        st.markdown(f"**{html.escape(post['title'][:110])}**")
                        st.caption(f"{post['source']} · {post['published_at']:%Y-%m-%d %H:%M} · 股票/关键词：{post['keyword']}")
                        st.link_button('查看原帖', post['url'], icon=':material/open_in_new:')
            else:
                st.info('其他平台暂无通过时间校验的近期讨论。')
        with st.expander('历史题材复盘样本'):
            st.caption('以下为有日期的历史资料，不属于近期讨论。')
            _render_captured_cards(CAPTURED_MARKET_HEAT)
    else:
        if view=='公司公告': st.caption('沪深京公开最新公告列表抽样，非全部公告；不在页面打开时联网抓取。')
        rows=[row for row in state['items'] if row['category']==view]
        if not rows: st.info(f'{view}暂无有效自动采集结果。')
        changed_ids = latest_changed_ids(directory)
        if changed_ids:
            st.caption('黄色标题 = 最近一次成功采集中新增或修订；其余为已有资讯。')
        for row in rows[:50]:
            with st.container(border=True):
                if row['id'] in changed_ids:
                    st.markdown(f"<strong style='color:#ffd54f'>✦ 新增/修订 · {html.escape(row['title'])}</strong>", unsafe_allow_html=True)
                else:
                    st.markdown(f"**{row['title']}**")
                published=row['published_at'] or '发布时间未知'
                st.caption(f"{row['source']} · {row['fact_type']} · {published}")
                if row.get('scheduled_at'):
                    planned=datetime.fromisoformat(row['scheduled_at']).astimezone(ZoneInfo('Asia/Shanghai'))
                    st.caption(f"计划发布时间：{planned:%Y-%m-%d %H:%M}（北京时间）；计划日程不代表数据已发布。")
                st.link_button('查看来源原文',row['url'],icon=':material/open_in_new:')
    if st.checkbox('查看早期历史样本（非最新资讯）', key='show_historical_news_samples'):
        _render_historical_sentiment_page(dict(data))
