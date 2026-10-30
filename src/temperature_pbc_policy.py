"""Capture the last completed month's PBC seven-day reverse repo rate."""
import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import pandas as pd

from src.temperature_data import validate_observations
from src.temperature_http import get_public


INDEX_URL = 'https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html'
RATE_COVERAGE = '中国人民银行7天期逆回购操作利率；2024-07-22前为利率招标中标利率，此后固定利率'


def _html(url):
    response = get_public(url, timeout=(5, 15))
    response.raise_for_status()
    if len(response.content) > 500_000:
        raise ValueError('央行公告页面过大')
    response.encoding = response.apparent_encoding or 'utf-8'
    return BeautifulSoup(response.text, 'html.parser')


def _published_at(text):
    match = re.search(r'文章来源[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', text)
    if not match:
        raise ValueError('央行公告缺发布时间')
    return pd.Timestamp(match.group(1), tz='Asia/Shanghai').tz_convert('UTC')


def collect_pbc_policy(captured_at=None):
    captured = pd.Timestamp.now(tz='UTC') if captured_at is None else pd.Timestamp(captured_at)
    if captured.tzinfo is None:
        raise ValueError('抓取时间必须带时区')
    captured = captured.tz_convert('UTC')
    latest_complete_month = captured.tz_convert('Asia/Shanghai').tz_localize(None).to_period('M') - 1
    index = _html(INDEX_URL)
    candidates = []
    for anchor in index.find_all('a', href=True):
        title = anchor.get_text(' ', strip=True)
        path = anchor['href']
        date_match = re.search(r'/(\d{8})\d+/index\.html$', path)
        if '公开市场业务交易公告' not in title or not date_match:
            continue
        notice_date = pd.Timestamp(date_match.group(1))
        if notice_date.to_period('M') == latest_complete_month:
            candidates.append((notice_date, urljoin(INDEX_URL, path)))
    if not candidates:
        raise ValueError(f'央行公告首页缺{latest_complete_month}月公告，未推测利率')
    for notice_date, url in sorted(candidates, reverse=True):
        text = _html(url).get_text(' ', strip=True)
        if '7天期逆回购操作量为零' in text:
            continue
        if not re.search(r'操作\s*利率', text):
            continue
        # PBC table cells may split digits with HTML spaces: "1. 40 %".
        rate_match = re.search(r'7\s*天\s*(\d+)\.\s*(\d+)\s*%', text)
        if not rate_match:
            continue
        rate = float(f'{rate_match.group(1)}.{rate_match.group(2)}')
        if not 0 < rate < 20:
            raise ValueError('央行7天利率超出合理范围')
        published = _published_at(text)
        if published > captured or notice_date.date() != published.tz_convert('Asia/Shanghai').date():
            raise ValueError('央行公告日期与抓取时间不一致')
        period = str(latest_complete_month)
        frame = pd.DataFrame([dict(indicator_id='cn_policy_rate', value=rate, unit='percent',
            market_coverage=RATE_COVERAGE, data_period=period, source_url=url,
            published_at=captured, completed_at=latest_complete_month.end_time.tz_localize('Asia/Shanghai').tz_convert('UTC'),
            fetched_at=captured, valid_until=captured + pd.Timedelta(days=1), revision=False,
            version='capture-' + hashlib.sha256(f'{period}|{rate}|{url}'.encode()).hexdigest()[:16],
            publication_basis='captured_dataset', original_publication_at=published,
            effective_event_date=notice_date.strftime('%Y-%m-%d'),
            announcement_index_url=INDEX_URL,
            calculation='完整月份内最后一份明确列出7天操作利率的公告；零操作日跳过',
            validity_basis='捕获后24小时重新核验；并非原始发布版本')])
        return validate_observations(frame)
    raise ValueError(f'{latest_complete_month}月公告均未列出7天操作利率，未沿用旧利率')
