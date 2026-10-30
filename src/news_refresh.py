"""Run outside Streamlit: python -m src.news_refresh --directory data/news."""
import argparse
from datetime import datetime,timezone
import json
import requests
from src.news_sources import SOURCES,fetch_source
from src.news_snapshot import save_news_run
from src.forum_hot import collect as collect_forum_hot, save as save_forum_hot
from src.taoguba_hot import collect as collect_taoguba_hot, save as save_taoguba_hot
from pathlib import Path

def refresh_news(directory='data/news',now=None):
    now=now or datetime.now(timezone.utc); items=[]; results=[]
    for key,config in SOURCES.items():
        result=dict(source=config['source'],category=config['category'],status='failed',error='',checked_at=now.isoformat())
        try:
            found=fetch_source(key,now)
            if not found: raise ValueError('来源返回空列表，未确认是有效零条')
            items.extend(found); result['status']='success'; result['count']=len(found)
        except requests.RequestException:
            result['error']='公开来源网络或HTTP请求失败，保留旧数据'
        except (ValueError,KeyError,TypeError,UnicodeError) as error:
            result['error']=str(error)[:180] if config.get('unsupported') else '列表格式或时间校验失败，保留旧数据'
        results.append(result)
    state = save_news_run(directory,items,results,now)
    try:
        save_forum_hot(Path(directory).parent / 'forum_hot', collect_forum_hot())
    except (requests.RequestException, ValueError, KeyError, TypeError, OSError) as error:
        print(f'股吧关注个股试采失败，保留旧快照：{error}')
    try:
        save_taoguba_hot(Path(directory).parent / 'taoguba_hot', collect_taoguba_hot())
    except (requests.RequestException, ValueError, KeyError, TypeError, OSError) as error:
        print(f'淘股吧关注个股试采失败，保留旧快照：{error}')
    return state

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--directory',default='data/news')
    state=refresh_news(parser.parse_args().directory)
    print(json.dumps({key:state[key] for key in ('last_success_at','new_count','source_results')},ensure_ascii=False))
