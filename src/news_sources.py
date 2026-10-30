"""Small bounded public-source adapters; no login or anti-bot bypass."""
import re
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
import requests
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from src.news_snapshot import validate_item

SOURCES={
    'pbc':dict(source='中国人民银行',category='政策监管',url='https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html',pattern=r'/goutongjiaoliu/113456/113469/\d+/index.html',fact_type='官方发布'),
    'media':dict(source='中国新闻网',category='新闻快讯',url='https://www.chinanews.com.cn/finance/',pattern=r'/cj/\d{4}/\d{2}-\d{2}/\d+\.shtml',fact_type='媒体报道'),
    'announcements':dict(source='巨潮资讯·深市',category='公司公告',url='https://www.cninfo.com.cn/new/disclosure',column='szse_latest'),
    'announcements_sse':dict(source='巨潮资讯·沪市',category='公司公告',url='https://www.cninfo.com.cn/new/disclosure',column='sse_latest'),
    'announcements_bj':dict(source='巨潮资讯·北交所',category='公司公告',url='https://www.cninfo.com.cn/new/disclosure',column='bj_latest'),
    'calendar':dict(source='国家统计局',category='宏观日历',url='https://www.stats.gov.cn/sj/fbrc/bnxxfb/'),
}

def parse_announcements(payload,source_id,now):
    config=SOURCES[source_id]; groups=payload.get('classifiedAnnouncements')
    if not isinstance(groups,list) or not groups: raise ValueError('empty announcement response')
    rows=[]
    for group in groups:
        if not isinstance(group,list): raise ValueError('invalid announcement grouping')
        for row in group:
            code=str(row['secCode']); name=row['secName']; link=row['adjunctUrl']
            if not re.fullmatch(r'\d{6}',code) or not name: raise ValueError('invalid security identity')
            if not re.fullmatch(r'finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF',link,re.I): raise ValueError('invalid source document')
            stamp=row['announcementTime']
            if isinstance(stamp,bool) or not isinstance(stamp,(int,float)): raise ValueError('invalid announcement time')
            published=datetime.fromtimestamp(stamp/1000,ZoneInfo('Asia/Shanghai'))
            title=BeautifulSoup(row['announcementTitle'],'html.parser').get_text(' ',strip=True)
            if not title: raise ValueError('empty announcement title')
            value=validate_item(dict(category='公司公告',title=f'{code} {name} · {title}',url='https://static.cninfo.com.cn/'+link,source=config['source'],published_at=published.isoformat(),captured_at=now.isoformat(),fact_type='公司披露原文',summary='最新公开公告列表抽样，非全市场公告全集；内容与披露时点以原文为准。'),now)
            if published>=now-timedelta(days=30): rows.append(value)
            if len(rows)>=50: return rows
    if not rows: raise ValueError('no valid recent announcements')
    return rows

def parse_calendar(html,now):
    """Expand the official two-row monthly schedule without shifting missing months."""
    soup=BeautifulSoup(html,'html.parser')
    year_match=re.search(r'(\d{4})年国家统计局主要统计信息发布日程表',soup.get_text(' ',strip=True))
    if not year_match: raise ValueError('official calendar year missing')
    year=int(year_match[1]); config=SOURCES['calendar']; rows=[]
    for table in soup.select('table'):
        grid={}
        for r,tr in enumerate(table.select('tr')):
            c=0
            for cell in tr.find_all(['td','th'],recursive=False):
                while (r,c) in grid: c+=1
                height=int(cell.get('rowspan',1)); width=int(cell.get('colspan',1))
                if not 1<=height<=20 or not 1<=width<=20: raise ValueError('invalid calendar span')
                text=cell.get_text(' ',strip=True)
                for dr in range(height):
                    for dc in range(width): grid[r+dr,c+dc]=text
                c+=width
        if [grid.get((0,c)) for c in range(2,14)]!=[f'{m}月' for m in range(1,13)]: continue
        for r in range(1,len(table.select('tr'))):
            if not re.fullmatch(r'\d+',grid.get((r,0),'')): continue
            title=grid.get((r,1),'')
            for month in range(1,13):
                date_text=grid.get((r,month+1),''); match=re.fullmatch(r'(\d{1,2})/([一二三四五六日])',date_text)
                if not match: continue
                time_text=grid.get((r+1,month+1),'')
                clock=re.fullmatch(r'(\d{1,2}):(\d{2})',time_text)
                if not clock: raise ValueError('official calendar time missing')
                scheduled=datetime(year,month,int(match[1]),int(clock[1]),int(clock[2]),tzinfo=ZoneInfo('Asia/Shanghai'))
                if '一二三四五六日'[scheduled.weekday()]!=match[2]: raise ValueError('calendar weekday mismatch')
                if not now-timedelta(days=30)<=scheduled<=now+timedelta(days=30): continue
                rows.append(validate_item(dict(category='宏观日历',title=f'{scheduled:%Y-%m-%d} {title}',url=config['url'],source=config['source'],published_at=None,scheduled_at=scheduled.isoformat(),captured_at=now.isoformat(),fact_type='官方计划日程',summary='官方计划发布时间；不代表数据已经发布，实际发布时间以官方更新为准。'),now))
    if not rows: raise ValueError('no verified calendar events')
    return sorted(rows,key=lambda row:row['scheduled_at'])[:50]

def parse_links(html,source_id,now):
    config=SOURCES[source_id]; soup=BeautifulSoup(html,'html.parser'); rows=[]; seen=set()
    for anchor in soup.select('a[href]'):
        url=urljoin(config['url'],anchor['href'])
        if urlsplit(url).hostname!=urlsplit(config['url']).hostname or not re.search(config['pattern'],url): continue
        title=anchor.get_text(' ',strip=True).strip('- ')
        if len(title)<6 or url in seen: continue
        # Listing titles can repeat an image alt label; retain no full article text.
        midpoint=len(title)//2
        if len(title)%2==1 and title[:midpoint]==title[midpoint+1:]: title=title[:midpoint]
        rows.append(validate_item(dict(category=config['category'],title=title,url=url,source=config['source'],published_at=None,captured_at=now.isoformat(),fact_type=config['fact_type'],summary=''),now))
        seen.add(url)
        if len(rows)>=50: break
    if not rows: raise ValueError('未取得可核验资讯列表，可能是空页或访问限制')
    return rows

def fetch_source(source_id,now):
    config=SOURCES[source_id]
    if config.get('unsupported'): raise ValueError(config['unsupported'])
    with requests.Session() as session:
        headers={'User-Agent':'MarketResearchSnapshot/1.0'}
        if config.get('column'):
            headers['Referer']='https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice'
            response=session.post(config['url'],data=dict(column=config['column'],pageNum=1,pageSize=17,sortName='',sortType='',clusterFlag='true'),timeout=10,headers=headers,allow_redirects=False)
        else:
            response=session.get(config['url'],timeout=10,headers=headers,allow_redirects=False)
        response.raise_for_status()
        if response.status_code!=200 or len(response.content)>3_000_000: raise ValueError('来源响应异常')
        if config.get('column'): return parse_announcements(response.json(),source_id,now)
        html=response.content.decode('utf-8')
        return parse_calendar(html,now) if source_id=='calendar' else parse_links(html,source_id,now)
