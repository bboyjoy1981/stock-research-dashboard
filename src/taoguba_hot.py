"""Small public Taoguba quote-page discussion snapshot for watched stocks."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
from urllib.parse import urldefrag
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import requests

from src.watchlist_store import load_watchlist

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo('Asia/Shanghai')


def collect(now=None):
    now = now or datetime.now(ZONE)
    posts = {}
    succeeded = []
    for code in load_watchlist(ROOT / 'data' / 'watchlist.json')[:12]:
        try:
            response = requests.get(f'https://www.tgb.cn/quotes/{code}', timeout=12,
                                    headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            if not soup.select('a[href*="/a/"]'):
                continue
            succeeded.append(code)
            for link in soup.select('a[href*="/a/"]')[:80]:
                url = urldefrag(link.get('href', ''))[0]
                if not re.fullmatch(r'https://www\.tgb\.cn/a/[A-Za-z0-9]+', url):
                    continue
                block = link.parent.parent.parent
                text = block.get_text(' ', strip=True)
                match = re.search(r'(20\d{2}-\d{2}-\d{2} \d{2}:\d{2})\s+(发布主帖|跟帖回复)', text)
                if not match or match[2] != '发布主帖':
                    continue
                published = datetime.strptime(match[1], '%Y-%m-%d %H:%M').replace(tzinfo=ZONE)
                if not (now - timedelta(hours=48) <= published <= now):
                    continue
                title = link.get_text(' ', strip=True) or text[match.end():].split('赞(')[0].strip()
                if len(title) < 8:
                    continue
                posts[url] = {'title': title[:160], 'url': url, 'source': '淘股吧',
                              'code': code, 'published_at': published.isoformat(),
                              'kind': match[2]}
        except (requests.RequestException, ValueError):
            continue
    if not succeeded:
        raise ValueError('淘股吧公开页面均不可用')
    return sorted(posts.values(), key=lambda row: row['published_at'], reverse=True)


def save(directory, posts, now=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'latest.json'
    payload = {'captured_at': (now or datetime.now(ZONE)).isoformat(), 'items': posts}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)
    return payload
