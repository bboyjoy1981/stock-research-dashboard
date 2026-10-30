"""Original public-news layout, fed only by an explicit audited source."""
import html
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import streamlit as st
from ..news_model import decode_news_dataset


def render(snapshot,capabilities,navigation):
    dataset=snapshot.optional.get('news')
    if dataset is None:
        st.title('热点舆情')
        st.info('公开资讯快照尚未发布；不使用历史样本冒充最新资讯。')
        return
    try:
        state=decode_news_dataset(dataset,datetime.now(timezone.utc))
    except (ValueError,TypeError,KeyError):
        st.title('热点舆情')
        st.warning('资讯快照校验未通过，暂不展示未经验证的数据。')
        return
    render_state(state,{'import_date':snapshot.metadata['date']},set(state['changed_ids']),navigation.namespace+'_')


def render_state(state,data,changed_ids,prefix=''):
    st.title('热点舆情')
    st.caption('公开政策与财经资讯 · 官方事实和媒体报道分开 · 不统计社交平台情绪')
    last = state['last_success_at']
    stamp = datetime.fromisoformat(last).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M') if last else '暂无成功记录'
    successes = sum(row['status']=='success' for row in state['source_results'])
    with st.container(horizontal=True):
        st.metric('最近成功采集', stamp, border=True)
        st.metric('本次新增或修订', state['new_count'], border=True)
        st.metric('有效资讯', len(state['items']), border=True)
        status='本次来源采集成功' if successes and successes==len(state['source_results']) else '部分来源可用' if successes else '本次采集失败 · 保留旧资讯' if last and state['items'] else '暂无有效采集'
        st.metric('采集状态', status, border=True)
    st.caption('只读公开资讯快照；采集任务独立运行。页面刷新不触发联网，不是盘中实时推送。')
    if not last:
        st.info('暂无有效采集；历史样本不会冒充最新资讯。')
    elif state['stale']:
        st.warning('超过12小时未成功采集，资讯可能过期；保留最后有效结果。')
    for result in state['source_results']:
        if result['status']!='success':
            st.warning(f"{result['category']} · {result['source']}：{result.get('error') or '采集失败'}")
    st.caption(f"行情快照：{data.get('import_date') or '未提供'}；资讯源时间逐条标注，采集时间不等于发布时间，不做同日涨跌归因。")
    view = st.segmented_control('信息分类', ['政策监管','公司公告','宏观日历','新闻快讯','市场热度'], default='政策监管', key=prefix+'market_signal_category') or '政策监管'
    if view=='市场热度':
        st.info('小红书及博客讨论尚未接入自动采集。未发布市场热度资料，不能把历史题材样本当作今日社交热度。')
    else:
        if view=='公司公告': st.caption('沪深京公开最新公告列表抽样，非全部公告；不在页面打开时联网抓取。')
        rows=[row for row in state['items'] if row['category']==view]
        if not rows: st.info(f'{view}暂无有效自动采集结果。')
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

    return view

