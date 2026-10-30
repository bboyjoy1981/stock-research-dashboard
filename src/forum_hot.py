"""Bounded public Eastmoney stock-bar watchlist capture."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests
from src.watchlist_store import load_watchlist

ZONE = ZoneInfo('Asia/Shanghai')
ROOT = Path(__file__).resolve().parents[1]
NAMES = {'688008': '澜起科技', '601127': '赛力斯', '002384': '东山精密',
         '601138': '工业富联', '300308': '中际旭创', '600522': '中天科技'}


def _views(label):
    match = re.search(r'([\d,.]+)\s*(万)?次浏览', label)
    if not match:
        return None
    return int(float(match[1].replace(',', '')) * (10000 if match[2] else 1))


def collect(now=None):
    now = now or datetime.now(ZONE)
    posts = {}
    codes = load_watchlist(ROOT / 'data' / 'watchlist.json')[:12]
    if not codes:
        raise ValueError('关注股票名单为空')
    succeeded, failed = [], []
    for code in codes:
        try:
            response = requests.get(f'https://mguba.eastmoney.com/mguba/list/{code}', timeout=12)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            if not soup.select_one('#items'):
                raise ValueError('未找到股吧列表')
        except (requests.RequestException, ValueError) as error:
            failed.append({'code': code, 'reason': str(error)[:120]})
            continue
        succeeded.append(code)
        for node in soup.select('#items > li')[:30]:
            abstract = node.select_one('p.abstract')
            clock = node.select_one('p.time')
            link = abstract.find_parent('a') if abstract else None
            if not (abstract and clock and link):
                continue
            href = link.get('href', '')
            if not re.fullmatch(r'/mguba/article/\d+/\d+', href):
                continue
            label = clock.get_text(' ', strip=True)
            match = re.search(r'(更新于|发表于)\s*(今天|昨天)\s*(\d{1,2}):(\d{2})', label)
            if not match:
                continue
            day = now.date() - timedelta(days=1 if match[2] == '昨天' else 0)
            updated = datetime(day.year, day.month, day.day, int(match[3]), int(match[4]), tzinfo=ZONE)
            if updated > now or now - updated > timedelta(hours=48):
                continue
            url = urljoin('https://mguba.eastmoney.com', href)
            posts[url] = dict(title=abstract.get_text(' ', strip=True)[:200], url=url,
                              source='东方财富股吧', code=code, stock=NAMES.get(code, code), updated_at=updated.isoformat(),
                              captured_at=now.isoformat(), views=_views(label),
                              time_basis='列表更新时间，非原帖发布时间' if match[1] == '更新于' else '列表发表时间')
    if not succeeded:
        raise ValueError('所有关注股票的股吧列表均采集失败')
    return {'items': sorted(posts.values(), key=lambda row: row['updated_at'], reverse=True),
            'requested_codes': codes, 'succeeded_codes': succeeded, 'failed': failed}


def save(directory, result, now=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'latest.json'
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'items': []}
    old_urls = {row['url'] for row in old.get('items', [])}
    failed_codes = {row['code'] for row in result['failed']}
    preserved = [row for row in old.get('items', []) if row.get('code') in failed_codes]
    posts = result['items'] + preserved
    posts.sort(key=lambda row: row['updated_at'], reverse=True)
    payload = dict(captured_at=(now or datetime.now(ZONE)).isoformat(), items=posts,
                   new_urls=[row['url'] for row in result['items'] if row['url'] not in old_urls],
                   requested_codes=result['requested_codes'], succeeded_codes=result['succeeded_codes'],
                   failed=result['failed'])
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)
    return payload
