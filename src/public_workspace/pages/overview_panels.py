"""Original source-free overview activity, maps, reports and snapshot review."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import html
import pandas as pd
import numpy as np
import streamlit as st
from ..report_model import activity_totals,activity_comparison,closing_report
from ...price_limits import confirmed_limit_counts,confirmed_limit_rows
from ...calculations import market_map_leaves
from ...industry_cloud import industry_cloud_figure
from ...snapshot_review import compare_saved_snapshots,snapshot_change_distribution,industry_snapshot_comparison
from .cloud_components import display_table,focus_sector,reset_scope


class OverviewPanels:
    def __init__(self,data,capabilities,navigation,prefix=""):
        self.data=data
        self.capabilities=capabilities
        self.navigation=navigation
        self.state=navigation.state
        self.prefix=prefix

    def table(self,frame,**kwargs):
        return display_table(frame,self.capabilities,**kwargs)

    def html(self,source):
        return st.html(source.replace('st-key-','st-key-'+self.prefix))

    def download(self,*args,**kwargs):
        if self.capabilities.download: return st.download_button(*args,**kwargs)

    def open_full_cloud(self):
        reset_scope(self.state,self.prefix)
        for suffix in ('area','hierarchy'):
            value=self.state.get(self.prefix+'overview_map_'+suffix)
            if value is not None:
                self.state[self.prefix+('terminal_size' if suffix=='area' else 'terminal_level')]=value
        self.state[self.prefix+'terminal_industry_query']=''
        self.state[self.prefix+'terminal_quick_group']='全市场'
        self.state[self.prefix+'terminal_workspace_mode']='一屏云图'
        return self.navigation.open_page('大盘云图')

    def focus_sector(self,field,value):
        if not focus_sector(self.data['stocks'],field,value,self.navigation):
            return False
        self.state[self.prefix+'terminal_industry_query']=value
        return True

    def open_stock(self,code):
        stocks=self.data['stocks']
        rows=stocks.loc[stocks['代码'].eq(code)]
        if rows.empty: return False
        row=rows.iloc[0]
        field=next((f for f in ('细分行业','行业','板块') if f in row and pd.notna(row[f]) and str(row[f]).strip()),None)
        industry=str(row[field]) if field else None
        parent=str(row['行业']) if field=='细分行业' and '行业' in row and pd.notna(row['行业']) else None
        if not self.navigation.open_stock(code,set(stocks['代码']),industry,parent): return False
        self.state[self.prefix+'stock_detail_query']=code
        self.state.pop(self.prefix+'stock_detail_selection',None)
        self.state[self.prefix+'research_context']=dict(source='市场总览',industry=industry,field=field,parent=parent)
        return True

    def open_limit_stock(self,members):
        code=self.state.get(self.prefix+'limits_stock')
        if '代码' in members and code in set(members['代码']):
            return self.open_stock(code)
        return False

    def reset_review_filters(self):
        for key in ('overview_compare_search','overview_compare_movement','overview_compare_industry','overview_compare_sort','overview_compare_direction','overview_compare_stock','overview_compare_page'):
            self.state.pop(self.prefix+key,None)

    def render_news_preview(self,market_date=None):
        state=self.data.get('public_news_state')
        with st.container(border=True):
            left,right=st.columns([4,1],vertical_alignment='center')
            with left:
                st.subheader('热点舆情速览',icon=':material/travel_explore:')
                if state is None:
                    st.info('公开资讯快照尚未发布；不使用历史样本冒充最新资讯。')
                else:
                    last=state.get('last_success_at')
                    stamp=datetime.fromisoformat(last).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M') if last else '暂无成功记录'
                    st.caption(f'最近成功采集：{stamp}｜官方事实与媒体报道分开；不是实时推送。')
                    if state.get('stale'): st.warning('资讯可能过期；保留最后有效结果。')
                    for item in state.get('items',[])[:3]:
                        st.markdown('**'+html.escape(item['category'])+'**　'+html.escape(item['title']))
                        st.caption(item['source']+'｜发布时间：'+str(item['published_at'] or '未提供'))
            with right:
                st.metric('社媒情绪样本','未接入',help='只使用已发布公开资讯快照；没有社交平台评论或情绪比例。')
                st.button('查看全部热点',icon=':material/arrow_forward:',key=self.prefix+'overview_open_market_sentiment',
                          on_click=self.navigation.open_page,args=('热点舆情',))

    def render_market_activity(self, data):
        # Only temperature is highlighted; activity and breadth retain dark cards.
        self.html('''<style>
        .st-key-pulse_market_state,
        .st-key-pulse_activity_amount {
            background: #101b2b !important;
            border: 1px solid #253c55 !important;
            box-shadow: none !important;
            min-height: 170px;
        }
        .st-key-pulse_market_state [data-testid="stMetricValue"],
        .st-key-pulse_activity_amount [data-testid="stMetricValue"] {
            font-size: 24px !important; white-space: normal !important;
        }
        .st-key-pulse_market_state [data-testid="stMetricValue"] div,
        .st-key-pulse_activity_amount [data-testid="stMetricValue"] div {
            white-space: normal !important; overflow: visible !important;
        }
        .st-key-pulse_market_state [data-testid="stMetric"],
        .st-key-pulse_activity_amount [data-testid="stMetric"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        .st-key-pulse_market_state [data-testid="stMetric"] *,
        .st-key-pulse_activity_amount [data-testid="stMetric"] *,
        .st-key-pulse_activity_volume [data-testid="stMetric"] * { color: #ffffff !important; }
        </style>''')
        totals = activity_totals(data)
        frame = data.get('stocks', pd.DataFrame())
        units = frame.get('成交量单位', pd.Series(index=frame.index, dtype=str))
        volume_unit = next((unit for unit in ('股', '手') if len(frame) > 0 and units.eq(unit).all()), None)
        known_hands = volume_unit is not None
        amount, volume = totals['成交额'], totals['成交量']
        total, valid, rows = amount
        display = '—' if total is None else f'{total / 1e12:.2f} 万亿元' if total >= 1e12 else f'{total / 1e8:,.2f} 亿元'
        volume_display = ('—' if volume[0] is None else f'{volume[0] / 1e8:,.2f} 亿{volume_unit}') if known_hands else '单位待核实'
        amount_delta,amount_note=activity_comparison(data,'成交额')
        volume_delta,volume_note=activity_comparison(data,'成交量')
        with st.container(key=self.prefix+'pulse_activity_amount', border=True, gap='xsmall'):
            st.metric('当日市场成交额', display, delta=amount_delta, delta_color='off', delta_arrow='off',
                      help=f'当前导入范围汇总；有效覆盖 {valid:,}/{rows:,}。不是交易所官方全市场统计。')
            st.caption(f'成交量：{volume_display} · {volume_delta}')
            if amount_note: st.caption(amount_note)
        with st.expander('成交统计口径与数据覆盖', expanded=False):
            if volume_note: st.caption(volume_note)
            if amount[0] is not None:
                st.caption(f'成交额精确值：{amount[0] / 1e8:,.2f} 亿元（当前导入范围汇总）。')
            unit_note = f'成交量单位：{volume_unit}（按快照单位记录；不只凭总手表头推断）。' if known_hands else '量沿用文件原始单位，未确认股/手前不擅自换算。'
            st.caption(f"成交额覆盖 {amount[1]:,}/{amount[2]:,}；成交量覆盖 {volume[1]:,}/{volume[2]:,}。{unit_note}")
            history = data.get('market_history', pd.DataFrame())
            dates = sorted(history['快照日期'].dropna().astype(str).unique()) if '快照日期' in history else []
            previous = [day for day in dates if day < str(data.get('import_date') or '')]
            if previous:
                st.caption(f'上个已保存快照：{previous[-1]}。尚未核实为上一交易日，无法计算昨日成交量增减；不会把较早快照标成昨天。')
            else:
                st.caption('缺少上一交易日的同口径快照，无法计算昨日成交量增减。')

    def render_closing_report(self, data, sectors, field):
        report = closing_report(data, sectors, field)
        st.subheader('收盘复盘报告', icon=':material/article:')
        self.download('下载收盘报告 Markdown', report.encode('utf-8'), file_name='market_close_report.md',
                           mime='text/markdown', icon=':material/download:', key=self.prefix+'overview_close_report_export')
        st.markdown(report)

    def render_limit_lists(self, stocks, date, snapshot=None):
        st.subheader('每日涨跌停汇总', icon=':material/format_list_bulleted:')
        if snapshot and snapshot.get('date') == date:
            st.caption(f"{date} · 收盘封板；不含盘中触板后打开。{snapshot['scope']}")
            choice = st.segmented_control('来源名单', ['涨停名单', '跌停名单'], default='涨停名单', key=self.prefix+'limits_provider_side')
            members = snapshot['down' if choice == '跌停名单' else 'up']
            if members:
                self.table(pd.DataFrame(members), hide_index=True, width='stretch')
            else:
                st.info('该来源口径下收盘封板为0家；不代表全A股为0家。')
            return
        frame = confirmed_limit_rows(stocks)
        covered = int(frame['限制价格有效'].sum())
        st.caption(f'快照日期：{date or "未提供"} · 限制价格覆盖 {covered:,}/{len(frame):,} 只 · 统计收盘封板，不含盘中触板后打开。')
        side = st.segmented_control('涨跌停名单', ['涨停名单', '跌停名单'], default='涨停名单', key=self.prefix+'limits_side') or '涨停名单'
        if not covered:
            st.info('缺少实际涨跌停价，暂无法生成准确名单。请补充当前交易日的涨停价、跌停价及收盘价；缺数据不代表零家。')
            return
        if covered < len(frame):
            st.warning('当前仅为已覆盖个股的名单，不代表全市场完整涨跌停名单。')
        members = frame.loc[frame['收盘涨停' if side == '涨停名单' else '收盘跌停']].copy()
        if members.empty:
            st.info(f'已覆盖样本中没有收盘{side[:2]}个股。')
            return
        columns = [field for field in ['代码', '名称', '细分行业', '行业', '价格', '涨跌幅', '成交额'] if field in members]
        self.table(members[columns], hide_index=True, width='stretch')
        if '代码' in members:
            names = dict(zip(members['代码'], members.get('名称', members['代码'])))
            code = st.selectbox('选择个股查看详情', members['代码'].tolist(),
                                format_func=lambda value: f'{value} · {names[value]}', key=self.prefix+'limits_stock')
            st.button('打开个股详情', key=self.prefix+'limits_open_stock', on_click=self.open_limit_stock, args=(members,))
        self.download('导出涨跌停名单', members[columns].to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'{date}_{side}.csv', mime='text/csv', key=self.prefix+'limits_export')

    def render_close_limit_metric(self, stocks, day, snapshot=None):
        import streamlit as st
        counts=confirmed_limit_counts(stocks)
        if counts['covered'] and counts['covered']==counts['total']:
            st.metric('涨停 / 跌停家数',f"{counts['up']:,} / {counts['down']:,}",border=True,
                      help='收盘价等于实际涨跌停价；不含盘中触板后打开。')
        elif snapshot and snapshot.get('date')==day:
            st.metric('收盘涨停 / 跌停（来源口径）',f"{len(snapshot['up']):,} / {len(snapshot['down']):,}",border=True,
                      help=f"{day}收盘封板，不含炸板。{snapshot['scope']}。来源：{snapshot['source']}。采集：{snapshot['captured_at']}")
            st.caption(snapshot['scope'])
        else:
            value=f"{counts['up']:,} / {counts['down']:,}" if counts['covered'] else '待补数据'
            st.metric('涨停 / 跌停家数（部分）' if counts['covered'] else '涨停 / 跌停家数',value,border=True,
                      help=f"限制价格覆盖{counts['covered']}/{counts['total']}只；缺数据不是零家。")

    def render_overview_map(self, stocks, hierarchy, size_field):
        """Industry-only map with explicit, selectable size weighting."""
        import plotly.express as px
        self.state[self.prefix+'overview_map_hierarchy'] = hierarchy
        area_options = [field for field in ('总市值', '流通市值', '成交额')
                        if field in stocks and pd.to_numeric(stocks[field], errors='coerce').gt(0).any()]
        if area_options:
            if self.state.get(self.prefix+'overview_map_area') not in area_options:
                self.state[self.prefix+'overview_map_area'] = area_options[0]
            size_field = st.selectbox('云图面积口径', area_options, key=self.prefix+'overview_map_area',
                                     help='总市值看规模，流通市值看流通规模，成交额看当天活跃度；均为板块成分股汇总。')
        parent = '行业' if hierarchy == '细分行业' and '行业' in stocks else None
        leaves = market_map_leaves(stocks, pd.DataFrame(), hierarchy, size_field or '等权', '涨跌幅', parent_field=parent)
        if leaves.empty:
            st.caption('当前快照没有有效涨跌与面积数据，无法绘制市场地图。')
            return
        grouping = ['行业', hierarchy] if hierarchy == '细分行业' and '行业' in leaves else [hierarchy]
        sectors = leaves.groupby(grouping, dropna=False).agg(面积=('面积','sum'), 云图颜色=('云图颜色','mean'),
                                                             涨跌幅=('涨跌幅','mean'), 成分股数=('个股','size')).reset_index()
        sectors['板块标签'] = sectors[hierarchy].astype(str) + '\n' + sectors['涨跌幅'].map(lambda value:f'{value:+.2f}%')
        tree = industry_cloud_figure(sectors, [*grouping[:-1], '板块标签'], height=720)
        st.plotly_chart(tree, width='stretch', key=self.prefix+'overview_market_map')
        with st.container(horizontal=True, vertical_alignment='center'):
            st.caption(f"{len(sectors)} 个板块 · 汇总 {len(leaves):,} 只有效成分股 · 面积={size_field or '等权'} · 红涨绿跌 · 板块等权涨跌非行业指数")
            st.button('展开完整云图', icon=':material/open_in_full:', key=self.prefix+'overview_full_cloud',
                      on_click=self.open_full_cloud)

    def render_market_snapshot_comparison(self, data):
        with st.expander("收盘快照变化对照", expanded=False, icon=":material/compare_arrows:"):
            st.subheader("收盘快照变化对照")
            history = data.get("market_history", pd.DataFrame())
            review = compare_saved_snapshots(history, through_date=data.get("import_date")) if data.get("stock_quote_source") == "imported" else {"stocks": pd.DataFrame()}
            if not review.get("current_date"):
                st.caption("至少保存两个交易日且包含相同股票后，可比较快照变化。")
                return
            prior_dates = sorted(history.loc[history["快照日期"].astype(str).lt(review["current_date"]), "快照日期"].astype(str).unique(), reverse=True)
            baseline = st.selectbox("对照交易日", prior_dates, key=self.prefix+"overview_compare_baseline", persist_state="session")
            review = compare_saved_snapshots(history, through_date=data.get("import_date"), baseline_date=baseline)
            frame = review["stocks"]
            st.caption(f"当前 {review['current_date']} ← 对照 {baseline}；按股票代码匹配，不要求两个保存日连续。")
            with st.container(horizontal=True):
                st.metric("共同样本", f"{len(frame):,}", border=True)
                st.metric("当前新增样本", f"{review['added']:,}", border=True)
                st.metric("当前缺少样本", f"{review['removed']:,}", border=True)
                mean_difference = frame["涨跌幅变化"].mean()
                st.metric("平均涨幅变化", f"{mean_difference:+.2f} 个百分点" if pd.notna(mean_difference) else "—", border=True)
            st.caption("新增或缺少指快照样本变化，不代表上市或退市。价格变化使用原始导入价格，未处理除权复权。")
            current_coverage = len(frame) / review["current_count"] * 100 if review["current_count"] else 0
            baseline_coverage = len(frame) / review["baseline_count"] * 100 if review["baseline_count"] else 0
            st.caption(f"共同样本占当前快照 {current_coverage:.1f}%，占对照快照 {baseline_coverage:.1f}%；这是导入样本覆盖率，不是全市场覆盖率。")
            if frame.empty:
                st.info("选定日期没有共同样本，请更换对照日期。")
                return
            view = st.segmented_control("复盘视图", ["个股变化", "行业变化"], default="个股变化", key=self.prefix+"overview_compare_view", persist_state="session") or "个股变化"
            filtered = frame.copy()
            stocks = data.get("stocks", pd.DataFrame())
            industry = "全部"
            if not stocks.empty and {"代码", "行业"}.issubset(stocks):
                st.caption("行业分类来自当前选定快照，不推断历史分类变化。")
                groups = stocks[["代码", "行业"]].copy()
                groups["代码"] = groups["代码"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
                groups["行业"] = groups["行业"].fillna("未分类").astype(str).str.strip().replace("", "未分类")
                filtered = filtered.merge(groups.drop_duplicates("代码", keep="last"), on="代码", how="left")
                filtered["行业"] = filtered["行业"].fillna("未分类")
                industry_components = filtered.copy()
                industry_board = industry_snapshot_comparison(filtered)
                if view == "行业变化":
                    self.render_industry_comparison_board(industry_board, review["current_date"], baseline, industry_components, expanded=True)
                    return
                industry = st.selectbox("变化榜行业", ["全部"] + sorted(filtered["行业"].unique()), key=self.prefix+"overview_compare_industry", persist_state="session")
                if industry != "全部":
                    filtered = filtered.loc[filtered["行业"].eq(industry)]
            elif view == "行业变化":
                st.info("当前快照缺少行业分类，暂不能生成行业变化榜。请补充行业字段；个股对照仍可使用。")
                return
            st.button("重置变化榜筛选", key=self.prefix+"overview_compare_reset", icon=":material/restart_alt:", on_click=self.reset_review_filters)
            search = st.text_input("搜索变化榜", placeholder="股票代码或名称", key=self.prefix+"overview_compare_search", persist_state="session").strip()
            movement = st.segmented_control("变化范围", ["全部", "涨幅走强", "涨幅走弱", "成交放大"], default="全部", key=self.prefix+"overview_compare_movement", persist_state="session") or "全部"
            if search:
                filtered = filtered.loc[filtered["代码"].str.contains(search, regex=False, na=False) | filtered["名称"].astype(str).str.contains(search, regex=False, na=False)]
            if movement == "涨幅走强":
                filtered = filtered.loc[filtered["涨跌幅变化"].gt(0)]
            elif movement == "涨幅走弱":
                filtered = filtered.loc[filtered["涨跌幅变化"].lt(0)]
            elif movement == "成交放大":
                filtered = filtered.loc[filtered["成交额倍数"].gt(1)]
            st.caption(f"筛选结果 {len(filtered):,} / 共同样本 {len(frame):,}；走强、走弱仅指当日涨跌幅相较对照日的变化。")
            if filtered.empty:
                st.info("没有符合当前条件的共同样本，请调整搜索或变化范围。")
                return
            st.caption("涨幅变化分布 · 单位：个百分点；统计当前筛选结果")
            valid_amounts = int(filtered["成交额倍数"].notna().sum())
            st.caption(f"成交额倍数有效样本 {valid_amounts} / {len(filtered)}；对照成交额缺失或为0时不计算倍数。成交额变化不等于资金净流入。")
            distribution = snapshot_change_distribution(filtered)
            st.bar_chart(distribution, x="区间", y="股票数", sort=False, width="stretch", height=180)
            sort_col, direction_col = st.columns([2, 1])
            sort_fields = {"涨幅变化": "涨跌幅变化", "当前涨幅": "涨跌幅_当前", "成交额倍数": "成交额倍数", "保存日价格变化": "价格变化"}
            with sort_col:
                sort_label = st.segmented_control("变化排行", list(sort_fields), default="涨幅变化", key=self.prefix+"overview_compare_sort", persist_state="session") or "涨幅变化"
            with direction_col:
                direction = st.segmented_control("排行方向", ["从高到低", "从低到高"], default="从高到低", key=self.prefix+"overview_compare_direction", persist_state="session") or "从高到低"
            ordered = filtered.sort_values(sort_fields[sort_label], ascending=direction == "从低到高", na_position="last")
            pages = max(1, (len(ordered) + 49) // 50)
            self.state[self.prefix+"overview_compare_page"] = max(1, min(int(self.state.get(self.prefix+"overview_compare_page", 1)), pages))
            page = st.number_input("变化榜页码", min_value=1, max_value=pages, step=1, key=self.prefix+"overview_compare_page", persist_state="session")
            visible = ordered.iloc[(page - 1) * 50:page * 50]
            st.caption(f"第 {page} / {pages} 页 · 当前显示 {len(visible)} 条，共 {len(ordered)} 条；导出不受分页限制。")
            self.table(visible, width="stretch", hide_index=True, column_config={
                "价格_当前": st.column_config.NumberColumn("当前价格", format="%.2f"),
                "价格_对照": st.column_config.NumberColumn("对照价格", format="%.2f"),
                "价格变化": st.column_config.NumberColumn("价格变化（未复权）", format="%+.2f%%"),
                "涨跌幅_当前": st.column_config.NumberColumn("当前当日涨跌", format="%+.2f%%"),
                "涨跌幅_对照": st.column_config.NumberColumn("对照当日涨跌", format="%+.2f%%"),
                "涨跌幅变化": st.column_config.NumberColumn("涨幅变化（百分点）", format="%+.2f"),
                "成交额_当前": st.column_config.NumberColumn("当前成交额", format="compact"),
                "成交额_对照": st.column_config.NumberColumn("对照成交额", format="compact"),
                "成交额倍数": st.column_config.NumberColumn("成交额倍数", format="%.2f 倍"),
            })
            labels = (visible["代码"] + " · " + visible["名称"].fillna("").astype(str)).tolist()
            with st.container(horizontal=True, vertical_alignment="bottom"):
                selected = st.selectbox("研究变化榜个股", labels, key=self.prefix+"overview_compare_stock")
                if st.button("打开变化榜研究卡", key=self.prefix+"overview_compare_open_stock", icon=":material/open_in_new:"):
                    self.open_stock(selected.split(" · ",1)[0])
                    st.rerun()
                if industry not in ("全部", "未分类") and st.button("在云图查看行业", key=self.prefix+"overview_compare_open_cloud", icon=":material/account_tree:"):
                    self.focus_sector("行业",industry)
                    st.rerun()
            export = ordered.assign(当前交易日=review["current_date"], 对照交易日=baseline)
            st.caption(f"导出包含全部 {len(ordered):,} 条筛选结果（每页最多50条）；行业：{industry}，范围：{movement}，排序：{sort_label} · {direction}。")
            self.download("导出快照变化榜 CSV", export.to_csv(index=False).encode("utf-8-sig"), f"快照对照_{review['current_date']}_{baseline}.csv", "text/csv", key=self.prefix+"overview_compare_export")
            difference_text = f"{mean_difference:+.2f}" if pd.notna(mean_difference) else "暂无数据"
            summary = f"收盘快照对照\n当前日期：{review['current_date']}\n对照日期：{baseline}\n共同样本：{len(frame)}\n筛选结果：{len(filtered)}\n变化范围：{movement}\n搜索条件：{search or '无'}\n新增样本：{review['added']}\n缺少样本：{review['removed']}\n全体共同样本平均涨幅变化（百分点）：{difference_text}\n说明：仅对共同样本作对照；原始价格未复权，成交额不等于资金净流入。\n"
            summary += f"行业条件：{industry}\n排序条件：{sort_label} · {direction}\n"
            self.download("导出复盘摘要", summary.encode("utf-8-sig"), f"复盘摘要_{review['current_date']}.txt", "text/plain", key=self.prefix+"overview_compare_summary")
            if "行业" in filtered:
                self.render_industry_comparison_board(industry_board, review["current_date"], baseline, industry_components)

    def render_industry_comparison_board(self, board, current_date, baseline, components=None, expanded=False):
        with st.expander("行业收盘变化榜", expanded=expanded, icon=":material/domain:"):
            st.caption(f"{baseline} → {current_date}；汇总全部共同样本，不受上方个股搜索影响。行业分类以当前快照为准。")
            sort_fields = {"平均涨幅变化": "平均涨幅变化", "走强比例": "走强比例", "成交额倍数": "成交额倍数", "共同样本": "共同样本"}
            mode = st.segmented_control("行业变化排序", list(sort_fields), default="平均涨幅变化", key=self.prefix+"review_industry_sort", persist_state="session") or "平均涨幅变化"
            direction = st.segmented_control("行业排行方向", ["从高到低", "从低到高"], default="从高到低", key=self.prefix+"review_industry_direction", persist_state="session") or "从高到低"
            minimum = st.number_input("行业最少共同样本", min_value=1, max_value=10000, value=1, step=1, key=self.prefix+"review_industry_minimum", persist_state="session")
            ordered = board.loc[board["共同样本"].ge(minimum)].sort_values(sort_fields[mode], ascending=direction == "从低到高", na_position="last")
            if ordered.empty:
                st.info("没有行业达到当前样本门槛，请降低最少共同样本数。")
                return
            chart = ordered.loc[ordered[sort_fields[mode]].notna()].head(15)
            if not chart.empty:
                st.caption(f"行业变化前15 · {mode} · {direction}；小样本行业的结果需谨慎解读。")
                st.bar_chart(chart, x="行业", y=sort_fields[mode], sort=False, width="stretch", height=220)
            self.table(ordered, width="stretch", hide_index=True, column_config={
                "平均涨幅变化": st.column_config.NumberColumn("平均涨幅变化（百分点）", format="%+.2f"),
                "走强比例": st.column_config.NumberColumn(format="%.1f%%"),
                "成交额覆盖率": st.column_config.NumberColumn(format="%.1f%%"),
                "成交额倍数": st.column_config.NumberColumn(format="%.2f 倍"),
            })
            st.caption("走强比例以涨幅变化有效股票为分母；行业成交额倍数为同一批有效样本的成交额总和之比，不是个股倍数平均值，也不是净流入。")
            names = ordered.loc[ordered["行业"].ne("未分类"), "行业"].tolist()
            if names:
                selected = st.selectbox("研究行业", names, key=self.prefix+"review_industry_selection", persist_state="session")
                row = ordered.loc[ordered["行业"].eq(selected)].iloc[0]
                with st.container(horizontal=True):
                    st.metric("行业共同样本", int(row["共同样本"]), border=True)
                    st.metric("行业平均涨幅变化", f"{row['平均涨幅变化']:+.2f} 个百分点" if pd.notna(row["平均涨幅变化"]) else "—", border=True)
                    st.metric("行业成交额覆盖率", f"{row['成交额覆盖率']:.1f}%", border=True)
                if components is not None and not components.empty:
                    peers = components.loc[components["行业"].eq(selected)].sort_values("涨跌幅变化", ascending=False, na_position="last")
                    st.caption(f"{selected} · 共同样本成分股（按涨幅变化排序，非完整行业成分名单）")
                    peer_fields = [field for field in ["代码", "名称", "涨跌幅_当前", "涨跌幅_对照", "涨跌幅变化", "成交额倍数"] if field in peers]
                    self.table(peers[peer_fields].head(20), width="stretch", hide_index=True, column_config={
                        "涨跌幅_当前": st.column_config.NumberColumn("当前当日涨跌", format="%+.2f%%"),
                        "涨跌幅_对照": st.column_config.NumberColumn("对照当日涨跌", format="%+.2f%%"),
                        "涨跌幅变化": st.column_config.NumberColumn("涨幅变化（百分点）", format="%+.2f"),
                        "成交额倍数": st.column_config.NumberColumn(format="%.2f 倍"),
                    })
                    st.caption(f"明细预览最多20条，个股选择与导出包含该行业全部 {len(peers)} 条共同样本。")
                    peer_labels = (peers["代码"].astype(str) + " · " + peers["名称"].fillna("").astype(str)).tolist()
                    if peer_labels:
                        peer = st.selectbox("研究行业成分股", peer_labels, key=self.prefix+"review_industry_stock")
                        if st.button("打开行业成分股研究卡", key=self.prefix+"review_industry_open_stock", icon=":material/open_in_new:"):
                            self.open_stock(peer.split(" · ",1)[0])
                            st.rerun()
                        self.download("导出当前行业共同样本", peers.assign(当前交易日=current_date, 对照交易日=baseline).to_csv(index=False).encode("utf-8-sig"), f"行业共同样本_{current_date}.csv", "text/csv", key=self.prefix+"review_industry_components_export")
                change_text = f"{row['平均涨幅变化']:+.2f} 个百分点" if pd.notna(row["平均涨幅变化"]) else "暂无数据"
                ratio_text = f"{row['成交额倍数']:.2f} 倍" if pd.notna(row["成交额倍数"]) else "暂无数据"
                industry_summary = f"行业收盘复盘：{selected}\n对照日期：{baseline} → {current_date}\n共同样本：{int(row['共同样本'])}\n涨幅有效样本：{int(row['涨幅有效样本'])}\n平均涨幅变化：{change_text}\n成交额有效样本：{int(row['成交额有效样本'])}\n成交额覆盖率：{row['成交额覆盖率']:.1f}%\n成交额倍数：{ratio_text}\n说明：当前快照行业分类；仅比较共同样本，不是完整行业成分名单。成交额不是资金净流入，本摘要不构成交易指令。\n"
                self.download("导出当前行业复盘摘要", industry_summary.encode("utf-8-sig"), f"行业复盘摘要_{current_date}.txt", "text/plain", key=self.prefix+"review_industry_summary_export")
                if st.button("打开行业云图", key=self.prefix+"review_industry_open_cloud", icon=":material/account_tree:"):
                    self.focus_sector("行业",selected)
                    st.rerun()
            self.download("导出行业变化榜", ordered.assign(当前交易日=current_date, 对照交易日=baseline).to_csv(index=False).encode("utf-8-sig"), f"行业变化_{current_date}_{baseline}.csv", "text/csv", key=self.prefix+"review_industry_export")

