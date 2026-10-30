"""Bounded public-release retrieval. No real-time feed, logins or fallback data."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import re

from bs4 import BeautifulSoup
import pandas as pd
import requests

from src.temperature_data import observations_at, validate_observations
from src.temperature_http import get_public

NBS_SCHEDULE = 'https://www.stats.gov.cn/xw/tjxw/tzgg/202512/t20251224_1962137.html'
# Explicit verified releases, not guessed URL patterns or an evergreen promise.
# Expiry follows the verified 2026 official schedule. A future registry update
# must verify each release and any changes to that schedule first.
from .public_workspace.temperature_registry import RELEASES

from .public_workspace.temperature_registry import PENDING_SOURCES


def parse_nbs_release(html, source_url, indicator_id, fetched_at, valid_until):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style']):
        tag.decompose()
    text = re.sub(r'\s+', '', soup.get_text(' ', strip=True))
    if any(marker in text for marker in ('验证码', 'AccessDenied', 'captcha')):
        raise ValueError('网站返回验证页，未采用数据')
    publication = re.search(r'发布时间[：:](\d{4}-\d{2}-\d{2})(\d{2}:\d{2})', text)
    if publication is None:
        publication = re.search(r'(?<!\d)(\d{4}/\d{2}/\d{2})(\d{2}:\d{2})(?!\d)', text)
    if publication is None:
        raise ValueError('缺少明确发布时间')
    published = pd.Timestamp(f'{publication[1].replace("/", "-")}T{publication[2]}:00', tz='Asia/Shanghai')
    if indicator_id == 'cn_pmi':
        period = re.search(r'(\d{4})年(\d{1,2})月中国采购经理指数运行情况', text)
        value = re.search(r'制造业采购经理指数[（(]PMI[）)]为([\d.]+)%', text)
        unit, coverage = 'index', '中国制造业；国家统计局PMI；经季节调整'
    elif indicator_id == 'cn_cpi_yoy':
        period = re.search(r'(\d{4})年(\d{1,2})月份居民消费价格', text)
        value = re.search(r'全国居民消费价格同比(上涨|下降|持平)(?:([\d.]+)%)?', text)
        unit, coverage = 'percent', '全国居民消费价格CPI；同比；未季调'
    else:
        raise ValueError('未支持的统计局指标')
    if period is None or value is None:
        raise ValueError('发布页字段变更或指标单位缺失')
    if indicator_id == 'cn_pmi':
        number = float(value[1])
        if not 0 <= number <= 100:
            raise ValueError('PMI值不在有效范围')
    else:
        if value[1] != '持平' and value[2] is None:
            raise ValueError('CPI百分比单位或数值缺失')
        number = 0 if value[1] == '持平' else float(value[2]) * (-1 if value[1] == '下降' else 1)
    record = dict(indicator_id=indicator_id, value=number, unit=unit,
        market_coverage=coverage, data_period=f'{period[1]}-{int(period[2]):02d}',
        source_url=source_url, published_at=published, completed_at=published,
        fetched_at=fetched_at, valid_until=valid_until,
        version='release-' + hashlib.sha256(f'{number}|{published.isoformat()}'.encode()).hexdigest()[:16],
        revision=False, schedule_url=NBS_SCHEDULE)
    return validate_observations(pd.DataFrame([record]))


def collect_temperature_sources(cutoff: pd.Timestamp) -> dict:
    cutoff = pd.Timestamp(cutoff)
    if cutoff.tzinfo is None:
        raise ValueError('采集截止必须带时区')
    fetched_at = pd.Timestamp.now(tz='UTC')

    def fetch(release):
        status = dict(来源=release['name'], 地址=release['url'], 状态='待采集', 说明='')
        if pd.Timestamp(release['published']) > cutoff:
            status.update(状态='截止后发布', 说明='不用于此复盘日')
            return pd.DataFrame(), status, None
        if pd.Timestamp(release['valid_until']) <= cutoff:
            status.update(状态='过期', 说明='已到下一次计划发布时间，需核验新发布页')
            return pd.DataFrame(), status, f"{release['name']}：已过期，未采集旧页冒充最新"
        try:
            response = get_public(release['url'], timeout=(5, 12))
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError('返回内容过大，拒绝解析')
            frame = parse_nbs_release(response.content.decode('utf-8'), release['url'],
                release['indicator_id'], fetched_at, pd.Timestamp(release['valid_until']))
            record = frame.iloc[0]
            if record['data_period'] != release['period'] or record['published_at'] != pd.Timestamp(release['published']):
                raise ValueError('发布期或发布时间与已核验记录不匹配')
            frame = observations_at(frame, cutoff)
            status.update(状态='已取得原始值', 说明='历史未齐；不代表此项已可评分')
            return frame, status, None
        except (requests.RequestException, ValueError, UnicodeError) as error:
            message = f"{release['name']}：{error}"
            status.update(状态='采集失败', 说明=message)
            return pd.DataFrame(), status, message

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(fetch, RELEASES))
    frames = [frame for frame, _, _ in results if not frame.empty]
    observations = validate_observations(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())
    statuses = [status for _, status, _ in results]
    statuses += [dict(来源=name, 地址=url, 状态='待接入', 说明=note) for name, url, note in PENDING_SOURCES]
    return dict(observations=observations, errors=[error for _, _, error in results if error],
                source_status=statuses, fetched_at=fetched_at.isoformat())
