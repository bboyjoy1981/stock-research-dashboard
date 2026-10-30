"""Original temperature view, exclusively over supplied observations and facts."""
import hashlib
import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
from ...price_limits import confirmed_limit_counts
from ...temperature_data import observations_at
from ...temperature_rules import GROUPS,METRICS,compare_temperature,evaluate_temperature
from ...temperature_stage import evaluate_trend_stage
from ..temperature_model import INDICATOR_GROUP,INDICATOR_NAMES,public_inputs
from ..temperature_registry import PENDING_SOURCES,RELEASES
from ..components import public_table
from ..contracts import PublicSnapshot


def render(snapshot,capabilities,navigation,headline_container=None):
    snapshot=PublicSnapshot(snapshot.stocks,snapshot.indices,dict(snapshot.metadata),dict(snapshot.optional))
    data=public_inputs(snapshot.optional.get('temperature'))
    data.update(stocks=snapshot.stocks,index_snapshot=snapshot.indices,stock_quote_source='imported',
        import_date=snapshot.metadata['date'])
    return TemperatureView(data,capabilities,navigation).render_market_temperature(data,headline_container)


@st.cache_data(max_entries=8,show_spinner=False)
def evaluate_cached(frame,cutoff):
    return evaluate_temperature(frame,cutoff)


@st.cache_data(max_entries=8,show_spinner=False)
def stage_cached(frame,cutoff):
    return evaluate_trend_stage(frame,cutoff)


class TemperatureView:
    def __init__(self,data,capabilities,navigation,prefix=None,owner_update_ui=None):
        self.data=data
        self.capabilities=capabilities
        self.state=navigation.state
        self.namespace=navigation.namespace
        self.prefix=navigation.namespace+'_' if prefix is None else prefix
        self.owner_update_ui=owner_update_ui if self.namespace=='owner' else None

    def table(self,frame,**kwargs):
        return public_table(frame,tuple(frame.columns),self.capabilities,**kwargs)

    def html(self,source):
        return st.html(source.replace('st-key-','st-key-'+self.prefix))

    def _evaluate(self, frame, cutoff):
        return evaluate_cached(frame, cutoff)

    def _stage(self, frame, cutoff):
        return stage_cached(frame, cutoff)

    def _latest_cutoff(self, data, frame, now=None):
        """Stable minute cache key, advancing at every eligibility/expiry event."""
        if 'temperature_latest_cutoff' in data:
            return pd.Timestamp(data['temperature_latest_cutoff'])
        now = pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
        cutoff = now.floor('min')
        for key in ('published_at', 'completed_at', 'fetched_at', 'valid_until'):
            if key not in frame:
                continue
            events = pd.to_datetime(frame[key], utc=True, errors='coerce')
            events = events[events.gt(cutoff) & events.le(now)]
            if not events.empty:
                cutoff = max(cutoff, events.max())
        return cutoff

    def _latest_overall_reference(self, data):
        """Evaluate latest captured inputs without backdating them into replay."""
        if data.get('temperature_latest_observations_error'):
            raise ValueError('Latest temperature input unavailable')
        frame = data.get('temperature_latest_observations', pd.DataFrame())
        cutoff = self._latest_cutoff(data, frame)
        macro_mask = frame['indicator_id'].map(INDICATOR_GROUP).eq('宏观环境')
        macro = frame.loc[macro_mask]
        if not macro.empty:
            from src.temperature_alignment import align_macro_history
            macro, _ = align_macro_history(macro, cutoff)
        latest = pd.concat([macro, frame.loc[~macro_mask]], ignore_index=True)
        from src.temperature_alignment import align_shared_daily_history
        latest, _ = align_shared_daily_history(latest, cutoff, ('sp500', 'nasdaq'))
        return self._evaluate(latest, cutoff), cutoff

    def _last_complete_reference(self, data,current=None):
        saved=data.get('temperature_last_complete')
        if current is None: return saved
        result,cutoff=current
        if result['internal_score'] is None or result['coverage']<100: return saved
        return dict(label=result['label'],score=result['internal_score'],coverage=result['coverage'],
                    cutoff=cutoff.isoformat(),input_signature=hashlib.sha256(repr(result['input_signature']).encode('utf-8')).hexdigest())

    def _render_latest_overall_reference(self, data):
        try:
            result, cutoff = self._latest_overall_reference(data)
        except (OSError, ValueError, TypeError, KeyError):
            st.caption('最新整体参考数据读取或对齐失败；历史复盘保持原样。')
            return
        groups = result['groups']
        group_text = ' · '.join(
            f"{name} {groups[name]['internal_score']:.1f}（{groups[name]['label']}）"
            if groups[name]['internal_score'] is not None else f"{name} 待补"
            for name in ('宏观环境', '海外股市', 'A股热度')
        )
        with st.container(border=True, key=self.prefix+'pulse_latest_overall_reference', gap='xsmall'):
            st.metric('最新整体研究参考', result['label'],
                      f"{result['internal_score']:.2f}/100" if result['internal_score'] is not None else None,
                      help='根据最新捕获的宏观、海外股市和A股数据独立核算；事后研究参考，不回写历史复盘，也不是实时行情或买卖建议。')
            st.caption(f"覆盖 {result['coverage']}% · 截至 {cutoff.tz_convert('Asia/Shanghai').strftime('%Y-%m-%d %H:%M')}（北京时间）")
            st.caption(group_text)
            st.caption('研究参考；与上方所选历史复盘日分开计算。数据更新后结果可能变化。')
            with st.expander('最新资料覆盖与缺口', expanded=False):
                rows = [dict(项目=metric['name'], 权重=f"{metric['weight']}%",
                             最新数据期=metric['period'] or '—', 状态=metric['label'],
                             缺口或依据=metric['reason'])
                        for metric in result['metrics'].values()]
                self.table(pd.DataFrame(rows), hide_index=True, width='stretch')
                st.caption('可用历史与同日组成均达标后才评分；旧数据不自动延长有效期。')

    def _trend_reference(self, data):
        """Post-capture diagnostic, never backdate captured data into the replay."""
        try:
            frame = data.get('temperature_latest_observations', pd.DataFrame())
            frame = frame.loc[frame['data_period'].le(str(data.get('import_date', '')))]
            cutoff = self._latest_cutoff(data, frame)
            result = self._stage(frame, cutoff)
            result['reference_basis'] = '最新捕获历史的事后参考，非原始发布时点回测'
            return result
        except (OSError, ValueError, TypeError):
            return dict(label='待补指数历史', indices=[], technology='待补科技指数历史',
                        annual_line=dict(level=None, status='数据读取或校验失败'))

    def _render_trend_details(self, data):
        stage = self._trend_reference(data)
        with st.expander('趋势阶段 · 本轮回撤、均线与动态年线'):
            st.markdown(f"**趋势阶段：{stage['label']} · 科技：{stage['technology']}**")
            st.caption('观察起点2024-09-24；最新捕获历史的事后参考，不覆盖所选复盘日温度。阶段不等于冷暖，不预设一直处于牛市。')
            records = []
            for item in stage['indices']:
                records.append(dict(指数=item['name'], 阶段=item['stage'], 数据期=item.get('period','—'),
                    收盘=item.get('close'), 本轮最高收盘=item.get('cycle_peak'),
                    最高收盘日期=item.get('cycle_peak_date','—'),
                    本轮回撤=f"{item['cycle_drawdown']:.2%}" if 'cycle_drawdown' in item else '缺数据',
                    **{'120日均线':item.get('ma120'), '250日均线':item.get('ma250'),
                       '120日均线20日斜率':f"{item['slope120']:.2%}" if 'slope120' in item else '缺数据',
                       '250日均线20日斜率':f"{item['slope250']:.2%}" if 'slope250' in item else '缺数据'},
                    依据或缺口=item['reason'], 来源=item.get('source','—')))
            if records:
                self.table(pd.DataFrame(records), hide_index=True)
            annual = stage['annual_line']
            if annual['level'] is not None:
                st.markdown(f"**上证年线：{annual['level']:,.2f}点 · {annual['status']}**")
                st.caption(f"截至{annual['period']} · 相对年线{annual['distance']:+.2%} · 连续{annual['below_sessions']}个有效收盘低于各自当日年线 · 年线20日变化{annual['slope']:+.2%}")
            else:
                st.caption(f"上证年线：{annual['status']}")
            st.caption('年线取最近250个有效交易日收盘均值，随数据更新；低于年线提示转弱，连续5个有效收盘低于年线且年线20日变化为负才提示下行确认，不等于熊市定论。实验条件待回测。')
            st.caption('实验规则：至少270个有效收盘并覆盖观察起点；3/5指数同档才判整体上升、结构转弱或下行，否则调整中。科技单看创业板与科创50。')
            st.caption('下行：低于120/250日均线且两均线20日斜率均负；结构转弱：低于250日均线且其斜率负，或连续3收盘低于此前20日最低收盘；上升：在两均线上、120日斜率正、250日斜率非负且本轮回撤不超过5%；其余调整中。阈值尚未回测。')

    def _fact_table(self, frame):
        if frame.empty:
            return pd.DataFrame()
        frame = frame.sort_values('data_period').drop_duplicates('indicator_id', keep='last').copy()
        result = pd.DataFrame({
            '指标': frame['indicator_id'].map(lambda key: INDICATOR_NAMES.get(key, key)),
            '原始值': frame['value'], '单位': frame['unit'], '数据期': frame['data_period'],
            '发布时间': frame['published_at'].map(lambda value: value.tz_convert('Asia/Shanghai').isoformat()),
            '抓取时间': frame['fetched_at'].map(lambda value: value.tz_convert('Asia/Shanghai').isoformat()),
            '来源': frame['source_url'], '口径': frame['market_coverage'], '版本': frame['version'],
        })
        return result.reset_index(drop=True)

    def _local_snapshot_facts(self, data):
        """Facts only: local imports have no verified original publication vintage."""
        frame = data.get('stocks', pd.DataFrame())
        if frame.empty or data.get('stock_quote_source') != 'imported':
            return
        change = pd.to_numeric(frame.get('涨跌幅', pd.Series(dtype=float)), errors='coerce')
        change = change[np.isfinite(change)]
        amount = pd.to_numeric(frame.get('成交额', pd.Series(dtype=float)), errors='coerce')
        amount = amount[np.isfinite(amount) & amount.ge(0)]
        limits = confirmed_limit_counts(frame)
        rows = [dict(指标='当日成交额', 原始事实=f'{amount.sum()/1e12:.2f}万亿元' if len(amount) else '缺数据',
                     覆盖=f'{len(amount)}/{len(frame)}只'),
                dict(指标='上涨占比', 原始事实=f'{change.gt(0).mean():.1%}' if len(change) else '缺数据',
                     覆盖=f'{len(change)}/{len(frame)}只'),
                dict(指标='实际收盘涨停/跌停', 原始事实=f"{limits['up']}/{limits['down']}" if limits['covered'] else '缺涨跌停价',
                     覆盖=f"{limits['covered']}/{limits['total']}只")]
        st.caption(f"本地行情事实 · {data.get('import_date')} · 用户导入范围汇总；历史和原始发布时间未齐，不直接评分。")
        self.table(pd.DataFrame(rows), hide_index=True)
        indices = data.get('index_snapshot', pd.DataFrame())
        if not indices.empty:
            fields = [key for key in ('名称', '价格', '涨跌幅', '交易日期', '源时间', '来源') if key in indices]
            self.table(indices[fields], hide_index=True)

    def temperature_weight_chart(self):
        frame = pd.DataFrame({'类别': list(GROUPS),
                              '权重': [value[0] for value in GROUPS.values()],
                              '标签': [f'{value[0]}%' for value in GROUPS.values()], '顺序': [0, 1, 2]})
        frame['模型'] = '组成权重'
        base = alt.Chart(frame).encode(x=alt.X('权重:Q', stack='zero', axis=None,
                                           scale=alt.Scale(domain=[0, 100])), y=alt.Y('模型:N', axis=None),
            order=alt.Order('顺序:Q'),
            color=alt.Color('类别:N', scale=alt.Scale(domain=frame['类别'].tolist(),
                           range=['#d8af50', '#3296bd', '#ef7667']), legend=None),
            tooltip=['类别:N', alt.Tooltip('权重:Q', title='模型权重（%）')])
        bars = base.mark_bar(size=32)
        labels = base.mark_text(dx=-14, fontSize=11, fontWeight='bold').encode(
            text='标签:N', color=alt.value('#101b2b'))
        return (bars + labels).properties(height=40, background='transparent').configure_view(stroke=None)

    def _render_temperature_headline(self, result, comparison, container=None, latest_reference=None,
                                     replay_day=None, last_complete=None):
        with container if container is not None else st.container():
            with st.container(border=True, key=self.prefix+'pulse_market_temperature_headline', gap='xsmall'):
                self.html('''<style>
                .st-key-pulse_market_temperature_headline {
                    min-height: 170px;
                }
                .st-key-pulse_market_temperature_headline [data-testid="stMetric"] {
                    background: transparent !important; border: none !important;
                    box-shadow: none !important; padding: 0 !important;
                }
                .st-key-pulse_market_temperature_headline [data-testid="stMetricValue"] {
                    font-size: 42px !important; font-weight: 800 !important;
                    line-height: 1.15 !important; white-space: normal !important;
                }
                .st-key-pulse_market_temperature_headline [data-testid="stMetricValue"] div {
                    white-space: normal !important; overflow: visible !important;
                }
                </style>''')
                if latest_reference is not None:
                    latest_result, latest_cutoff = latest_reference
                    latest_score = latest_result['internal_score']
                    showing_saved = latest_score is None and last_complete is not None
                    displayed = last_complete if showing_saved else dict(
                        label=latest_result['label'], score=latest_score)
                    st.metric('最近一次完整结果 · 已过期' if showing_saved else '最新整体市场温度 · 研究参考',
                              displayed['label'],
                              help='按最新捕获的宏观15%、海外20%、A股65%数据计算；不是实时行情。')
                    score = displayed['score']
                    st.markdown(f"**综合分数：{score:.2f}/100**" if score is not None
                                else '**综合分数：资料不足**')
                    if showing_saved:
                        saved_at = pd.Timestamp(last_complete['cutoff']).tz_convert('Asia/Shanghai')
                        st.warning(f"这是 {saved_at.strftime('%Y-%m-%d %H:%M')} 的完整研究结果；当前仅覆盖"
                                   f" {latest_result['coverage']:.0f}%，暂不能给出新的整体判断。")
                        missing_names = [latest_result['metrics'][key]['name']
                                         for key in latest_result['missing']
                                         if key in latest_result['metrics']]
                        if missing_names:
                            st.caption('当前缺口：' + '、'.join(missing_names))
                    else:
                        st.caption(
                            f"可评分覆盖 {latest_result['coverage']:.0f}% · 数据核算截至 "
                            f"{latest_cutoff.tz_convert('Asia/Shanghai').strftime('%Y-%m-%d %H:%M')}（北京时间）"
                        )
                else:
                    if last_complete is not None:
                        saved_at = pd.Timestamp(last_complete['cutoff']).tz_convert('Asia/Shanghai')
                        st.metric('最近一次完整结果 · 当前数据读取失败', last_complete['label'])
                        st.markdown(f"**综合分数：{last_complete['score']:.2f}/100**")
                        st.warning(f"结果核算于 {saved_at.strftime('%Y-%m-%d %H:%M')}，当前数据读取失败。")
                    else:
                        st.metric('最新整体市场温度 · 研究参考', '暂无法判断')
                        st.caption('最新研究数据读取失败，请在详情中查看缺口。')
                st.caption(f"历史复盘（{replay_day or '未选交易日'}）：{result['label']}"
                           + (f" · {result['coverage']:.0f}%覆盖" if 'coverage' in result else '')
                           + '；与上方最新参考分开计算。')
                stage = result.get('trend_stage', {})
                st.caption(f"趋势阶段：{stage.get('label', '待补指数历史')} · 独立研究参考")
                if stage.get('reference_basis'):
                    periods = [item['period'] for item in stage.get('indices', []) if item.get('period')]
                    st.caption(f"截至{max(periods) if periods else '缺数据'} · 事后参考 · 科技：{stage.get('technology', '待补数据')}")
                opened = st.button('查看详情', icon=':material/arrow_forward:', key=self.prefix+'open_market_temperature',
                                 help='查看宏观、海外和A股的原始数据及核算依据。')
            st.altair_chart(self.temperature_weight_chart(), width='stretch', theme=None)
            st.caption('判断标准：宏观环境 15% · 海外股市 20% · A股热度 65%（组成权重，非数据覆盖率；新规则待历史验证）')
            st.caption('过冷 → 偏冷 → 中性 → 偏热 → 过热；缺关键数据时不判断冷暖。')
            return opened

    def _render_commodity_quotes(self):
        """Latest reviewed display snapshot, separate from historical grading."""
        st.markdown('#### 黄金与原油 · 分开看价格')
        st.caption('人工核实快照中的已完成日价格；不计入所选复盘日评分，不与盘中报价混比。')
        try:
            snapshot = self.data.get('temperature_commodity_review') or {}
            checked = pd.Timestamp(snapshot['checked_at'])
            if pd.isna(checked) or checked.tzinfo is None:
                raise ValueError('核实时间缺时区')
            quotes = snapshot['quotes']
            if len(quotes) != 2 or {item['id'] for item in quotes} != {'gold', 'oil'}:
                raise ValueError('缺完整品种')
            for item in quotes:
                for key in ('name', 'benchmark', 'unit', 'date', 'previous_date', 'availability', 'source_name', 'source_url'):
                    if not isinstance(item[key], str) or not item[key].strip():
                        raise ValueError('缺价格口径')
                if not all(np.isfinite(float(item[key])) and float(item[key]) > 0 for key in ('price', 'previous_price')):
                    raise ValueError('价格异常')
                if not pd.Timestamp(item['previous_date']) < pd.Timestamp(item['date']) <= checked.tz_convert('UTC').tz_localize(None):
                    raise ValueError('价格日期异常')
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            st.caption('缺已核实价格快照；暂不展示估算价格。')
            return
        stale = pd.Timestamp.now(tz='UTC') - checked > pd.Timedelta(days=1)
        st.caption('快照已过期，需重新核实；以下仅为历史参考。' if stale else '本次核实的来源最新已发布日价格；来源可能滞后。')
        for column, item in zip(st.columns(2), quotes):
            with column.container(border=True, key=self.prefix+f"temperature_quote_{item['id']}", gap='xsmall'):
                current, previous = float(item['price']), float(item['previous_price'])
                delta = current - previous
                st.metric(item['name'], f'{current:,.2f}',
                          delta=f'{delta:+,.2f} / {delta / previous:+.2%}', delta_color='off')
                st.badge('日价格上涨' if delta > 0 else '日价格下跌' if delta < 0 else '日价格持平',
                         color='red' if delta > 0 else 'green' if delta < 0 else 'gray')
                st.caption(f"{item['benchmark']} · {item['unit']}")
                st.caption(f"行情日期：{item['date']}（来源交易日）")
                st.caption(f"对比：{item['previous_date']} · {previous:,.2f} {item['unit']}")
                st.caption(item['availability'])
                st.markdown(f"[价格来源：{item['source_name']}]({item['source_url']})")
        st.caption(f"人工核实快照：{checked.tz_convert('Asia/Shanghai').strftime('%Y-%m-%d %H:%M')}（北京时间）；非自动刷新。日涨跌不等同20日趋势或市场温度。")

    def _render_environment_facts(self):
        """Reviewed news snapshot is explanatory, never an input to historical grades."""
        with st.container(key=self.prefix+'temperature_environment_facts', border=True):
            st.markdown('#### 利率决议与外围风险 · 最新核实摘要')
            try:
                review = self.data.get('temperature_environment_review') or {}
                checked = pd.Timestamp(review['checked_at'])
                if pd.isna(checked) or checked.tzinfo is None:
                    raise ValueError('核实时间缺时区')
                for section, fields in (('policy', ('name', 'decision_date', 'result', 'rate', 'source_url')),
                                        ('risks', ('name', 'status', 'fact', 'report_date', 'source_name', 'verification', 'source_url', 'watch'))):
                    if not isinstance(review[section], list) or not review[section]:
                        raise ValueError('缺摘要')
                    for item in review[section]:
                        if not all(isinstance(item[key], str) and item[key].strip() for key in fields):
                            raise ValueError('缺摘要字段')
            except (OSError, ValueError, TypeError, KeyError):
                st.caption('缺已核实摘要；不据此判断风险低。')
                return
            elapsed = pd.Timestamp.now(tz='UTC') - checked
            freshness = '需重新核实' if elapsed > pd.Timedelta(days=1) else '本次人工核实'
            st.caption(f"核实时间：{checked.tz_convert('Asia/Shanghai').strftime('%Y-%m-%d %H:%M')} · {freshness}；最新摘要不计入所选复盘日的温度评分。")
            st.markdown('**最近一次利率决议**')
            for start in range(0, len(review['policy']), 2):
                for column, item in zip(st.columns(2), review['policy'][start:start+2]):
                    with column.container(border=True, gap='xsmall'):
                        st.markdown(f"**{item['name']}**")
                        st.badge(item.get('headline', '待核实'), color=item.get('color', 'orange'))
                        st.markdown(f"**{item['rate']}**")
                        st.caption(f"决议日期：{item['decision_date']}")
                        with st.expander(f"{item['name']} · 决议说明与来源"):
                            st.markdown(item['result'])
                            st.markdown(f"[来源原文]({item['source_url']})")
            st.caption('单次决议不等于完整加降息周期；周期评分仍需90日变化及可比历史。中国政策利率使用7天逆回购，不用LPR替代。')
            for column, item in zip(st.columns(2), review['risks']):
                with column.container(border=True):
                    st.markdown(f"**{item['name']}**")
                    st.badge(item.get('headline', '进展待核实'), color='orange')
                    st.caption(f"报道日期：{item['report_date']} · 当日战况未确认")
                    with st.expander(f"{item['name']} · 报道依据与来源"):
                        st.markdown(item['status'])
                        st.markdown(item['fact'])
                        st.caption(f"{item['source_name']} · {item['verification']}")
                        st.markdown(f"[查看原始报道]({item['source_url']})")
                        st.caption(f"研究关注（非已发生结果）：{item['watch']}")
            st.caption('地缘风险独立提示，不按“存在战争”自动加减分；报道中的声称与研究机构判断不作为已独立确认的战果。')

    def _render_latest_overseas(self, data):
        if data.get('temperature_latest_observations_error'):
            st.caption('最新海外数据读取失败；保留历史复盘，不生成结论。')
            return
        from ..overseas_model import overseas_summary
        from src.temperature_alignment import align_shared_daily_history
        try:
            observations = data.get('temperature_latest_observations',pd.DataFrame())
            cutoff = self._latest_cutoff(data, observations)
            summary = overseas_summary(observations, cutoff)
            # Match the latest overall reference: US indices use their latest
            # shared completed trading date, without filling either series.
            aligned, shared_day = align_shared_daily_history(observations, cutoff, ('sp500', 'nasdaq'))
            result = self._evaluate(aligned, cutoff)
        except (OSError, ValueError, TypeError):
            st.caption('最新海外数据读取失败；保留历史复盘，不生成结论。')
            return
        if observations.empty:
            st.caption('最新海外收盘序列尚未接入。')
            return
        group = result['groups']['海外股市']
        with st.container(border=True, key=self.prefix+'temperature_latest_overseas'):
            st.markdown(f"# 最新分项判断 · 海外股市：{self._conclusion_badge(group['label'])}")
            self._render_time_basis('海外股市', result, '各市场最新已完成交易日（下表逐市场列出）')
            st.caption(f"单独计算海外股市，可评分权重 {group['available']}/{GROUPS['海外股市'][0]}；不覆盖所选历史复盘，也不代表整体市场温度。")
            if shared_day:
                st.caption(f'标普500与纳斯达克共同有效交易日：{shared_day}；未用盘中值或补齐缺日。')
            st.caption('采用来源最新已完成交易日；本次捕获的历史可能含修订，不作为历史时点回测。非实时刷新。')
            self.table(summary, hide_index=True)
            with st.expander('海外分项结论与全部核算依据'):
                metrics = [dict(指标=item['name'], 判断=item['label'], 依据或缺口=item['reason'])
                           for item in result['metrics'].values() if item['group'] == '海外股市']
                self.table(pd.DataFrame(metrics), hide_index=True)
                self.table(pd.DataFrame([item for item in result.get('calculation_audit', [])
                                          if INDICATOR_GROUP.get(item.get('indicator_id')) == '海外股市']), hide_index=True)
                self.table(observations[observations['indicator_id'].map(INDICATOR_GROUP).eq('海外股市')], hide_index=True)

    def _render_latest_research(self, data, group_name):
        """Captured research is displayed separately, never backdated into replay."""
        if data.get('temperature_latest_observations_error'):
            st.caption(f'最新{group_name}研究数据读取失败；不生成结论。')
            return
        try:
            frame = data.get('temperature_latest_observations', pd.DataFrame())
            frame = frame[frame['indicator_id'].map(INDICATOR_GROUP).eq(group_name)]
            cutoff = self._latest_cutoff(data, frame)
            if frame.empty:
                st.caption(f'最新{group_name}研究历史尚未接入。')
                return
            aligned, alignment_audit = frame, []
            if group_name == '宏观环境':
                from src.temperature_alignment import align_macro_history
                aligned, alignment_audit = align_macro_history(frame, cutoff)
            result = self._evaluate(aligned, cutoff)
            fresh = observations_at(frame, cutoff)
        except (OSError, ValueError, TypeError):
            st.caption(f'最新{group_name}研究数据读取失败；不生成结论。')
            return
        group = result['groups'][group_name]
        title = f'最新分项判断 · {group_name}'
        with st.container(border=True):
            st.markdown(f"# {title}：{self._conclusion_badge(group['label'])}")
            st.caption(f"可评分权重 {group['available']}/{GROUPS[group_name][0]}；不覆盖所选历史复盘，也不代表整体市场温度。")
            st.caption(f'计算截至：{cutoff.tz_convert("Asia/Shanghai").strftime("%Y-%m-%d %H:%M")}（北京时间）；各指标数据期分别列示。抓取后的事后研究，非历史时点回测；不自动刷新或延长有效期。')
            if alignment_audit:
                st.caption('同步核算口径：政策及金油组合取各组成真实存在的最近共同数据期；最新单项原始值仍在下表保留，不与组合基准日混用。')
                self.table(pd.DataFrame(alignment_audit), hide_index=True)
            self._render_time_basis(group_name, result, '本次研究核算时刻；各指标数据期见表')
            metrics = [dict(指标=item['name'], 判断=item['label'], 依据或缺口=item['reason'])
                       for item in result['metrics'].values() if item['group'] == group_name]
            if group_name == 'A股热度':
                for column, item in zip(st.columns(4), metrics):
                    with column.container(border=True):
                        st.caption(item['指标'])
                        st.markdown(f"### {self._conclusion_badge(item['判断'])}")
                with st.expander('四项摘要 · 判断依据与缺口', expanded=False):
                    self.table(pd.DataFrame(metrics), hide_index=True)
                with st.expander('导入快照 · 逐日上涨占比与资料核验', expanded=False):
                    snapshots = data.get('temperature_import_audit',pd.DataFrame())
                    if snapshots.empty:
                        st.caption('尚无可核验的逐日导入快照。')
                    else:
                        official_amount = (frame[frame['indicator_id'].eq('a_amount')]
                                           .sort_values('published_at')
                                           .drop_duplicates('data_period', keep='last')
                                           .set_index('data_period')['value'])
                        snapshots['对官方成交额覆盖'] = snapshots.apply(
                            lambda row: row['样本成交额（万亿元）'] * 1e14 / official_amount[row['数据期']]
                            if row['数据期'] in official_amount.index and official_amount[row['数据期']] > 0
                            else None, axis=1)
                        snapshots['核验提示'] = snapshots.apply(
                            lambda row: '收盘前源文件' if row['时点风险'] == '收盘前' else
                            '成交额覆盖不足' if pd.notna(row['对官方成交额覆盖'])
                            and row['对官方成交额覆盖'] < 99.5 else
                            '缺来源文件元数据' if row['原始文件信息'] == '缺' else
                            '仅样本描述', axis=1)
                        self.table(snapshots, hide_index=True, width='stretch',
                                     column_config={'上涨占比': st.column_config.NumberColumn(format='%.1f%%'),
                                                    '对官方成交额覆盖': st.column_config.NumberColumn(format='%.1f%%')})
                        st.caption('上涨占比只针对导入文件中有有效报价的股票；未证实覆盖沪深全部A股，不进入市场温度评分。')
                        st.caption('源文件时刻取本地文件修改时间或导入元数据；它不是交易所发布时间。10月16日核对原文件与导入价格一致，但原文件记录于14:59:25。')
                        st.caption('文件缺每只股票的实际涨跌停价，不能确认收盘涨跌停；60日高低点还需要同口径连续历史。')
            else:
                self.table(pd.DataFrame(metrics), hide_index=True)
            if group_name == 'A股热度':
                comparison_frame = frame
                try:
                    reference = data.get('temperature_comparison_observations',pd.DataFrame())
                    if not reference.empty:
                        comparison_frame = pd.concat([frame, reference], ignore_index=True)
                except (OSError, ValueError, TypeError):
                    st.caption('历史对比库读取失败；不影响温度核算，不使用损坏参考。')
                self._render_historical_comparisons(comparison_frame, cutoff)
            with st.expander(f'{group_name} · 最新原始值与来源', expanded=False):
                self.table(self._fact_table(fresh), hide_index=True)
            with st.expander(f'{group_name} · 最新研究全部原始历史与核算'):
                self.table(pd.DataFrame(result.get('calculation_audit', [])), hide_index=True)
                self.table(frame, hide_index=True)

    def _render_historical_comparisons(self, frame, cutoff):
        from src.temperature_comparison import compare_history, format_comparison_value
        st.markdown('### 当前水平 · 历史阶段对比')
        st.caption('独立描述性对比，不改变市场温度评分。分位低于20%为偏低，高于80%为偏高；不是牛熊判定。仅比较同指标、同单位、同市场范围；当前期不进入参考样本。')
        names = {'a_new_accounts': '沪市A股月度新开户账户数',
                 'a_margin_balance': '融资融券余额', 'a_margin_buy_ratio': '融资买入占成交额比例',
                 'a_amount': 'A股成交额'}
        names.update({key: name for key, name in INDICATOR_NAMES.items()
                      if INDICATOR_GROUP.get(key) == 'A股热度' and key not in names
                      and key in ('sse', 'szse', 'chinext', 'star50', 'csi300')})
        summary = []
        for indicator, name in names.items():
            monthly = indicator == 'a_new_accounts'
            for title, start, end in [('2015年', '2015-01', '2015-12-31'),
                                      ('9·24后', '2024-10' if monthly else '2024-09-24', '9999')]:
                item = compare_history(frame, cutoff, indicator, start, end, 12 if monthly else 120)
                if monthly and title == '2015年' and 'current' in item:
                    from src.temperature_comparison import compare_2015_accounts
                    reference = compare_2015_accounts(item['current'])
                    item.update(reference, start='2015-01', end='2015-12')
                difference = item.get('difference_pct')
                summary.append(dict(指标=name, 当前值=format_comparison_value(item['current'], item['unit']) if 'current' in item else '缺数据',
                    数据期=item.get('current_period', '—'), 对比时期=title, 结论=item['label'],
                    较参考均值=f'{difference:+.1f}%' if difference is not None else '—',
                    实际参考区间=f"{item['start']} 至 {item['end']}" if 'mean' in item else '历史不足'))
        self.table(pd.DataFrame(summary), hide_index=True)
        with st.expander('历史对比 · 展开各指标详细依据', expanded=False):
            self._render_comparison_explanations(frame, cutoff, names)

    def _render_comparison_explanations(self, frame, cutoff, names):
        from src.temperature_comparison import compare_history, format_comparison_value
        for indicator, name in names.items():
            monthly = indicator == 'a_new_accounts'
            with st.expander(f'{name} · 历史对比详情', expanded=False):
                st.markdown(f'#### {name}')
                for title, start, end in [('2015年', '2015-01', '2015-12-31'),
                                           ('9·24后', '2024-10' if monthly else '2024-09-24', '9999')]:
                    result = compare_history(frame, cutoff, indicator, start, end, 12 if monthly else 120)
                    if monthly and title == '2015年' and 'current' in result:
                        from src.temperature_comparison import compare_2015_accounts
                        reference = compare_2015_accounts(result['current'])
                        st.markdown(f"### 2015年：:red[**{reference['label']}**]")
                        st.markdown(f"当前 **{result['current']/10000:,.2f}万户**（{result['current_period']}）；2015年月均 **{reference['mean']/10000:,.2f}万户**，差距 **{reference['difference_pct']:+.1f}%**。")
                        st.markdown(f"2015年4月峰值 **{reference['peak']/10000:,.2f}万户**；当前较峰值 **{reference['peak_difference_pct']:+.1f}%**。")
                        st.markdown(f"2015年4—6月高开户阶段月均 **{reference['spring_mean']/10000:.2f}万户**；当前 **{reference['spring_difference_pct']:+.1f}%**。")
                        st.markdown(f"2015年7—9月回落阶段月均 **{reference['summer_mean']/10000:.2f}万户**；当前 **{reference['summer_difference_pct']:+.1f}%**。")
                        st.caption('以上两个日历区间分别只有3个月，描述账户数量差距，不是统计显著性结论，也不代表股灾期间每天的市场情绪。')
                        st.caption(f"[上交所2016卷年鉴·印刷页563]({reference['source']}#page=567)：2015年1—12月沪市A股新开户账户数，12个月；使用逐月值计算，合计与印刷年合计存在0.01万户舍入差异。事后历史参考，不计入温度或回测。")
                        continue
                    color = 'orange' if result['label'] == '暂不可比' else 'red'
                    st.markdown(f"### {title}：:{color}[**{result['label']}**]")
                    if 'mean' in result:
                        difference = result['difference_pct']
                        gap = f'{difference:+.1f}%' if difference is not None else '基准为零，不计算百分比'
                        current_text = format_comparison_value(result['current'], result['unit'])
                        mean_text = format_comparison_value(result['mean'], result['unit'])
                        peak_text = format_comparison_value(result['peak'], result['unit'])
                        st.markdown(f"当前 **{current_text}**（{result['current_period']}）；参考期均值 **{mean_text}**；差距 **{gap}**。")
                        peak_gap = (result['current'] / result['peak'] - 1) * 100 if result['peak'] else None
                        peak_difference = f'{peak_gap:+.1f}%' if peak_gap is not None else '基准为零，不计算百分比'
                        st.markdown(f"参考期最高 **{peak_text}**（{result['peak_period']}）；当前较最高值 **{peak_difference}**。")
                        st.caption(f"实际参考期 {result['start']} 至 {result['end']}，{result['count']} 个样本；单位 {result['unit']}。范围：{result['scope']}")
                        if result['start'] > start:
                            st.caption('注意：历史未覆盖请求起点，以上仅代表实际已取得区间，不能解释为整个阶段的统计。')
                    st.caption(result['reason'])
                if monthly:
                    st.caption('开户数不是新增投资者人数。2015年一人多户制度变化影响账户数量；即使取得同口径历史，也不能将差距解释为同等人数变化。月度9·24后从2024年10月完整月份起算。')
                if indicator == 'a_margin_balance':
                    st.caption('余额包括融资及融券，可能含符合条件的ETF；金额高低不等于杠杆风险高低，还需结合市场规模和买入占比。')

    def _conclusion_badge(self, label):
        color = 'orange' if label == '暂无法判断' else 'red'
        return f':{color}[**{label}**]'

    def _render_time_basis(self, group, result, cutoff_text):
        if group not in ('海外股市', 'A股热度'):
            return
        with st.container(border=True):
            st.caption('测算口径 · 时间与比较标准')
            st.caption(f'核算截至：{cutoff_text}')
            if group == '海外股市':
                st.caption('观察窗口：5日 / 20日涨跌幅 + 60日均线偏离。短中期热度，不是长期牛熊判断。')
            else:
                st.caption('冷热窗口：指数5/20日涨跌、60日线；成交相对20日均额；两融5日变化与买入占比。情绪含60日新高新低；开户只作对比，不计分。')
                st.caption('独立趋势起点：2024-09-24；参考回撤及120/250日线，不预设科技牛市。')
            st.caption('历史比较区间：使用核算截至时已发布的全部可用有效历史；当前期不参与历史分位。不是固定近一年，也不统一从924开始。')
            rows = [dict(指标=INDICATOR_NAMES.get(item['indicator_id'], item['indicator_id']),
                         计算项=item['calculation'], 当前数据期=item.get('current_period', '—'),
                         历史开始=item.get('history_start') or '缺数据', 历史结束=item.get('history_end') or '缺数据',
                         有效历史样本=item['history_count'], 最少要求=item['minimum'])
                    for item in result.get('calculation_audit', [])
                    if INDICATOR_GROUP.get(item.get('indicator_id')) == group]
            if rows:
                with st.expander('时间口径 · 各项实际历史区间', expanded=False):
                    self.table(pd.DataFrame(rows), hide_index=True)
            else:
                st.caption('尚无可计算历史，无法给出实际比较区间；不据此生成冷热结论。')

    def _input_catalog(self, fresh, group=None):
        facts = self._fact_table(fresh)
        catalog = pd.DataFrame({'指标': [INDICATOR_NAMES[key] for key in INDICATOR_GROUP],
                                '类别': list(INDICATOR_GROUP.values())})
        if group is not None:
            catalog = catalog[catalog['类别'].eq(group)]
        if facts.empty:
            catalog['原始值'] = None
            catalog['接入状态'] = '缺数据'
            return catalog
        catalog = catalog.merge(facts, on='指标', how='left')
        catalog['接入状态'] = np.where(catalog['原始值'].notna(), '已取得原始值；历史另核', '缺数据')
        return catalog

    def _render_temperature_details(self, data: dict) -> None:
        day = data.get('import_date')
        if not day:
            st.caption('需真实复盘日。')
            return
        cutoff = pd.Timestamp(str(day)).tz_localize('Asia/Shanghai') + pd.Timedelta(hours=15)
        errors = []
        supplied = data.get('temperature_observations', pd.DataFrame())
        try:
            stored = data.get('temperature_stored_observations',pd.DataFrame())
            observations = pd.concat([stored, supplied], ignore_index=True)
        except (OSError, ValueError) as error:
            observations = pd.DataFrame()
            errors.append(f'观测读取失败：{error}')

        with st.container(key=self.prefix+'pulse_market_temperature', gap='xsmall'):
            if self.owner_update_ui is not None and self.namespace=='owner':
                observations=self.owner_update_ui(data,cutoff)
            try:
                result = self._evaluate(observations, cutoff)
                fresh = observations_at(observations, cutoff)
            except (ValueError, TypeError) as error:
                errors.append(f'数据校验未通过：{error}')
                result = self._evaluate(pd.DataFrame(), cutoff)
                fresh = pd.DataFrame()
            calendar = data.get('temperature_trading_dates', [])
            previous = data.get('temperature_previous_result')
            comparison = compare_temperature(result, previous, calendar)
            with st.container(gap='small'):
                st.caption('以下优先显示最新采集数据的分项结果；所选日期的历史复盘另在折叠区核对。')
                icons = {'宏观环境': 'public', '海外股市': 'show_chart', 'A股热度': 'local_fire_department'}
                self.html('''<style>
                .st-key-temperature_group button {
                    background-color: #16283f !important;
                    border-color: #456386 !important;
                    color: #d9eaff !important;
                }
                .st-key-temperature_group button * { color: inherit !important; }
                .st-key-temperature_group button[aria-checked="true"] {
                    background-color: #1766c2 !important;
                    border-color: #72b5ff !important;
                    color: #ffffff !important;
                }
                .st-key-temperature_group button:hover {
                    background-color: #244265 !important;
                    color: #ffffff !important;
                }
                .st-key-temperature_group button[aria-checked="true"]:hover {
                    background-color: #1c73d6 !important;
                }
                </style>''')
                selected = st.segmented_control('市场温度板块', list(GROUPS), default='宏观环境',
                    required=True, key=self.prefix+'temperature_group', label_visibility='collapsed', width='stretch',
                    format_func=lambda group: f":material/{icons[group]}: **{group} · {GROUPS[group][0]}%**")
                for group, (weight, threshold) in GROUPS.items():
                    if group != selected:
                        continue
                    with st.container():
                        group_result = result['groups'][group]
                        if group == '海外股市':
                            self._render_latest_overseas(data)
                        else:
                            self._render_latest_research(data, group)
                        if group == '宏观环境':
                            self._render_environment_facts()
                            self._render_commodity_quotes()
                        with st.expander(f'历史复盘 · {day} · {group_result["label"]}（{group_result["available"]}/{weight}覆盖）', expanded=False):
                            st.caption(f'复盘截止：{day} 15:00（北京时间）；按当时可得资料核算，不使用后来补采的数据。')
                            self._render_time_basis(group, result, f'{day} 15:00（北京时间，所选历史复盘日）')
                            records = [dict(指标=metric['name'], 权重=f"{metric['weight']}%", 判断=metric['label'],
                                        数据期=metric['period'] or '—', 依据或缺口=metric['reason'])
                                   for key, metric in result['metrics'].items()
                                   if metric['group'] == group and key != 'commodities']
                            self.table(pd.DataFrame(records), hide_index=True)
                            if not fresh.empty:
                                group_facts = fresh[fresh['indicator_id'].map(INDICATOR_GROUP).eq(group)]
                                if not group_facts.empty:
                                    self.table(self._fact_table(group_facts), hide_index=True)
                        if group == 'A股热度':
                            with st.expander('A股 · 导入快照原始值', expanded=False):
                                self._local_snapshot_facts(data)
                            self._render_trend_details(data)
                            st.caption('趋势阶段与温度独立：年线下方不自动等于过冷，市场偏热也不抵消趋势转弱。')
                        if group == '宏观环境':
                            st.caption('PMI：水平与3月变化；通胀及政策变化用反向历史分位，属于环境代理而非经济定律；黄金上涨不自动等于股市利好。')
                        if group == '海外股市':
                            st.caption('固定标普500、纳斯达克、日经225、KOSPI；采用已完成交易时段的5/20日收益及60日均线距离。')
                with st.expander(f'历史复盘 · {selected} · 原始输入与逐项核算', expanded=False):
                    self.table(self._input_catalog(fresh, selected), hide_index=True)
                    audit = pd.DataFrame([item for item in result.get('calculation_audit', [])
                        if INDICATOR_GROUP.get(item.get('indicator_id')) == selected])
                    if audit.empty:
                        st.caption('尚无可计算的原始输入；分项表列出缺口，不生成虚构衍生值。')
                    else:
                        audit['indicator_id'] = audit['indicator_id'].map(lambda key: INDICATOR_NAMES.get(key, key))
                        self.table(audit.rename(columns={'indicator_id': '指标', 'calculation': '计算项',
                            'value': '当前衍生值', 'history_count': '有效历史样本数', 'minimum': '最低历史样本数',
                            'percentile': '历史分位（%）', 'inverse': '是否反向', 'label': '分项温度', 'reason': '核算说明'}), hide_index=True)
                with st.expander(f'{selected} · 数据来源与采集缺口', expanded=False):
                    statuses = self.state.get(self.prefix+'temperature_source_status')
                    fallback_statuses = statuses is None
                    if statuses is None:
                        statuses = [dict(来源=item['name'], 地址=item['url'], 状态='可按需采集', 说明='已核验此发布页；不代表历史已齐') for item in RELEASES]
                        statuses += [dict(来源=name, 地址=url, 状态='待接入', 说明=note) for name, url, note in PENDING_SOURCES]
                    source_groups = {'沪市两融': 'A股热度', '深市两融': 'A股热度', '新增开户': 'A股热度',
                        '海外指数及商品': '海外股市', '标普500': '海外股市', '纳斯达克': '海外股市',
                        '日经225': '海外股市', 'KOSPI': '海外股市', '海外指数历史': '海外股市'}
                    statuses = [item for item in statuses if
                        INDICATOR_GROUP.get(item.get('indicator_id', item.get('指标')),
                            source_groups.get(item.get('来源'), '宏观环境')) == selected]
                    if selected == 'A股热度' and fallback_statuses:
                        st.caption('本板块已取得数据以“最新原始值与来源”为准；下列入口登记不代表当前接入状态。')
                        statuses = [dict(item, 状态='备用披露入口', 说明='旧入口登记；实际已取得数据与历史范围请查看本板块核算明细。') for item in statuses]
                    if statuses:
                        self.table(pd.DataFrame(statuses), hide_index=True)
                    else:
                        st.caption('本板块没有单独的采集状态记录；实际已取得数据与缺口见本板块核算表。')
                    st.caption('采集状态仅记录对应任务，不等同于原始值或历史齐全；以核算明细为准。')
                    updated = self.state.get(self.prefix+'temperature_updated_at')
                    if updated:
                        st.caption(f'最近尝试更新时间：{updated}')
                st.caption('至少120个有效日历史或36个有效月历史，且复合项组成齐全后才评分；不把缺项填成中性。总覆盖需≥90%，三组分别≥12/15、16/20、58.5/65；保留原组内80%/80%/90%门槛。')
                st.caption('开户数仅作辅助信息，不再独立计分。A股组成：情绪25%、成交20%、指数短中期强弱10%、两融与参与度10%；趋势阶段及外围风险不被温度平均掉。')
            for error in errors + self.state.get(self.prefix+'temperature_update_errors', []):
                st.warning(error)
            if st.button('关闭详情', key=self.prefix+'close_market_temperature'):
                self.state[self.prefix+'temperature_details_open'] = False
                st.rerun()

    def render_market_temperature(self, data: dict, headline_container=None) -> None:
        day = data.get('import_date')
        try:
            latest_reference = self._latest_overall_reference(data)
        except (OSError, ValueError, TypeError):
            latest_reference = None
        last_complete = self._last_complete_reference(data, latest_reference)
        if day:
            cutoff = pd.Timestamp(str(day)).tz_localize('Asia/Shanghai') + pd.Timedelta(hours=15)
            try:
                observations = pd.concat([data.get('temperature_stored_observations',pd.DataFrame()),
                                          data.get('temperature_observations', pd.DataFrame())], ignore_index=True)
                result = self._evaluate(observations, cutoff)
            except (OSError, ValueError, TypeError):
                result = self._evaluate(pd.DataFrame(), cutoff)
            comparison = compare_temperature(result, data.get('temperature_previous_result'),
                                             data.get('temperature_trading_dates', []))
            result['trend_stage'] = self._trend_reference(data)
        else:
            result = dict(label='暂无法判断', internal_score=None)
            comparison = dict(direction='需真实复盘日')
        if self._render_temperature_headline(result, comparison, headline_container, latest_reference, day,
                                        last_complete):
            self.state[self.prefix+'temperature_details_open'] = True
        if self.state.get(self.prefix+'temperature_details_open', False):
            self._render_temperature_details(data)

