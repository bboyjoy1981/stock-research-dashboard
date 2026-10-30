from datetime import datetime,timezone
import importlib
import pytest
NOW=datetime(2026,10,13,8,tzinfo=timezone.utc)
def mod():
    try: return importlib.import_module('src.news_sources')
    except ModuleNotFoundError: pytest.fail('news sources not implemented')
def test_media_only_collects_article_links_with_unknown_time():
    html='<html><a href="/cj/2026/10-13/10713749.shtml">可核验财经新闻标题</a><a href="/about">关于我们</a></html>'
    rows=mod().parse_links(html,'media',NOW)
    assert len(rows)==1 and rows[0]['published_at'] is None
    assert rows[0]['url']=='https://www.chinanews.com.cn/cj/2026/10-13/10713749.shtml'
def test_empty_or_block_page_not_success():
    with pytest.raises(ValueError): mod().parse_links('<html>请登录 验证码</html>','media',NOW)
def test_official_links_not_conflated_with_media():
    rows=mod().parse_links('<a href="/goutongjiaoliu/113456/113469/2026101011293518009/index.html">中国人民银行发布公开通知</a>','pbc',NOW)
    assert rows[0]['category']=='政策监管' and rows[0]['fact_type']=='官方发布'
