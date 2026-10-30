"""Read recent, source-linked MediaCrawler posts without treating old search hits as hot."""
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo('Asia/Shanghai')
SOURCES = {'tieba': ('百度贴吧', 'note_url', 'publish_time')}


def recent_posts(root, now=None, max_age=timedelta(hours=48)):
    now = now or datetime.now(SHANGHAI)
    root = Path(root)
    posts = {}
    for platform, (source, url_key, time_key) in SOURCES.items():
        folder = root / 'data' / platform / 'jsonl'
        for path in folder.glob('search_contents_*.jsonl'):
            for line in path.read_text(encoding='utf-8').splitlines():
                try:
                    item = json.loads(line)
                    published = datetime.fromisoformat(item[time_key]).replace(tzinfo=SHANGHAI)
                    url = item[url_key]
                    if not (now - max_age <= published <= now) or not url.startswith('https://tieba.baidu.com/p/'):
                        continue
                    posts[url] = dict(title=item['title'][:200], url=url, source=source,
                                      published_at=published, keyword=item.get('source_keyword', ''))
                except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                    continue
    return sorted(posts.values(), key=lambda post: post['published_at'], reverse=True)
