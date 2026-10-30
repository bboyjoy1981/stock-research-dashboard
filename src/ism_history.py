"""Bounded ISM-issued headline PMI history; capture vintages, never PIT releases."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import StringIO
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import pandas as pd
import requests

from src.temperature_data import validate_observations
from src.temperature_http import get_public

REPORTS = (
    ('2022-09', 'https://www.prnewswire.com/news-releases/manufacturing-pmi-at-50-9-september-2022-manufacturing-ism-report-on-business-301638361.html'),
    ('2023-09', 'https://www.prnewswire.com/news-releases/manufacturing-pmi-at-49-september-2023-manufacturing-ism-report-on-business-301943535.html'),
    ('2024-09', 'https://www.prnewswire.com/news-releases/manufacturing-pmi-at-47-2-september-2024-manufacturing-ism-report-on-business-302263093.html'),
    ('2025-09', 'https://www.prnewswire.com/news-releases/manufacturing-pmi-at-49-1-september-2025-ism-manufacturing-pmi-report-302571530.html'),
    ('2026-09', 'https://www.prnewswire.com/news-releases/manufacturing-pmi-at-54-5-september-2026-ism-manufacturing-pmi-report-302894520.html'),
)
NEWSROOM = 'https://www.prnewswire.com/news/institute-for-supply-management/'
MONTHS = 'January February March April May June July August September October November December'.split()


def latest_newsroom_report(captured_at):
    response = get_public(NEWSROOM, timeout=(5, 15))
    response.raise_for_status()
    if len(response.content) > 1_000_000:
        raise ValueError('ISM发布者目录响应过大')
    last_complete = captured_at.tz_convert('America/New_York').tz_localize(None).to_period('M') - 1
    found = []
    for anchor in BeautifulSoup(response.text, 'html.parser').find_all('a', href=True):
        title = anchor.get_text(' ', strip=True)
        if 'Manufacturing PMI' not in title or 'ISM' not in title or 'Services PMI' in title:
            continue
        match = re.search(r'\b(' + '|'.join(MONTHS) + r')\s+(\d{4})\s+ISM', title)
        if not match:
            continue
        period = pd.Timestamp(f'{match.group(1)} {match.group(2)}').to_period('M')
        url = urljoin(NEWSROOM, anchor['href'])
        if period <= last_complete and url.startswith('https://www.prnewswire.com/news-releases/'):
            found.append((period, url))
    if not found:
        raise ValueError('ISM发布者目录没有可核验的制造业PMI报告')
    period, url = max(found, key=lambda item: item[0])
    return str(period), url


def parse_ism_history(html, source_url, report_period, captured_at):
    captured = pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError('抓取时间必须带时区')
    text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
    if 'Institute for Supply Management' not in text:
        raise ValueError('未确认ISM发布者')
    if any(word in text.lower() for word in ('access denied', 'captcha')):
        raise ValueError('来源访问受限')
    end = pd.Period(report_period, freq='M')
    values = {}
    for table in pd.read_html(StringIO(html)):
        if 'Manufacturing PMI' not in table.to_string() or 'Month' not in table.to_string():
            continue
        for row in table.itertuples(index=False, name=None):
            for index in range(0, len(row) - 1, 2):
                date = str(row[index]).strip()
                if not re.fullmatch(r'[A-Za-z]{3,9} \d{4}', date):
                    continue
                period = pd.Timestamp(date).to_period('M')
                value = float(row[index + 1])
                if not 0 <= value <= 100 or period > end or period < end - 11:
                    raise ValueError('历史PMI日期或数值超出报告范围')
                if period in values and values[period] != value:
                    raise ValueError('同月PMI冲突')
                values[period] = value
    if end not in values:
        raise ValueError('未取得报告当月制造业PMI历史表')
    rows = []
    for period, value in sorted(values.items()):
        completed = period.end_time.tz_localize('America/New_York')
        if completed > captured:
            raise ValueError('不采用尚未完成月份')
        rows.append(dict(indicator_id='us_pmi', unit='index',
            market_coverage='美国制造业；ISM Manufacturing PMI；季调分项合成',
            data_period=str(period), value=value, source_url=source_url,
            published_at=captured, fetched_at=captured, completed_at=completed,
            valid_until=captured + pd.Timedelta(days=1), revision=False,
            version='capture-' + hashlib.sha256(f'{source_url}|{period}|{value}'.encode()).hexdigest()[:16],
            publication_basis='captured_dataset',
            calculation='ISM发布报告中的12个月制造业总体PMI；非服务业及分项',
            validity_basis='本次抓取后24小时需重新核验；历史可能修订，非旧发布时点版本'))
    return validate_observations(pd.DataFrame(rows))


def collect_ism_history(captured_at=None):
    captured = pd.Timestamp.now(tz='UTC') if captured_at is None else pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError('抓取时间必须带时区')
    captured = captured.tz_convert('UTC')
    reports = list(REPORTS)
    discovery_status = []
    try:
        discovered = latest_newsroom_report(captured)
        if discovered not in reports:
            reports.append(discovered)
        discovery_status.append(dict(指标='us_pmi', 来源=NEWSROOM, 状态='已核验发布者目录',
                                     最近数据期=discovered[0]))
    except (requests.RequestException, ValueError) as error:
        discovery_status.append(dict(指标='us_pmi', 来源=NEWSROOM, 状态='失败', 说明=str(error)))

    def fetch(report):
        period, url = report
        try:
            response = get_public(url, timeout=(5, 15))
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError('报告响应过大')
            frame = parse_ism_history(response.text, url, period, captured)
            return frame, dict(指标='us_pmi', 报告期=period, 来源=url, 样本数=len(frame), 状态='已取得历史')
        except (requests.RequestException, ValueError) as error:
            return pd.DataFrame(), dict(指标='us_pmi', 报告期=period, 来源=url, 状态='失败', 说明=str(error))
    results = list(ThreadPoolExecutor(max_workers=5).map(fetch, reports))
    frames = [frame for frame, _ in results if not frame.empty]
    return dict(observations=validate_observations(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()),
                source_status=discovery_status + [status for _, status in results],
                fetched_at=captured.isoformat())
