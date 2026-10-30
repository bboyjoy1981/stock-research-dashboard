"""Deployment checks are read-only and fail closed against changed baselines."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
import pytest


def fixture_bundle(tmp_path):
    root=tmp_path/'site'
    (root/'src').mkdir(parents=True)
    public=root/'data'/'friends_public_20261020_comparison'
    public.mkdir(parents=True)
    (root/'data'/'friends_public').symlink_to(public,target_is_directory=True)
    old=b'old-public'
    (public/'stocks.csv').write_bytes(old)
    (public/'metadata.json').write_text(json.dumps({'date':'2026-10-20'}),encoding='utf-8')
    (root/'src'/'friends_pages.py').write_bytes(b'old-page')
    (root/'src'/'friends_data.py').write_bytes(b'old-data')
    names=['src/friends_pages.py','src/friends_data.py','src/industry_cloud.py','src/friends_cloud.py',
        'src/friends_research.py','src/friends_trend.py','src/friends_deep.py','deploy/preflight_cloud.py']
    entries={name:b'pass\n' for name in names}
    entries['public/stocks.csv']=('代码,名称,板块,价格,涨跌幅,成交额,行业,细分行业,流通市值,总市值\n'
        '000001,测试,主板,10,1,100,电子,设备,1000,2000\n').encode('utf-8-sig')
    sha=lambda raw:hashlib.sha256(raw).hexdigest()
    before={name:None for name in names if name.startswith('src/')}
    before.update({'src/friends_pages.py':sha(b'old-page'),'src/friends_data.py':sha(b'old-data'),
        'public/stocks.csv':sha(old)})
    manifest=dict(version=1,expected_before=before,after={name:sha(raw) for name,raw in entries.items()},
        date='2026-10-20',rows=1)
    archive=tmp_path/'bundle.zip'
    def write():
        manifest['after']={name:sha(raw) for name,raw in entries.items()}
        with zipfile.ZipFile(archive,'w') as z:
            for name,raw in entries.items(): z.writestr(name,raw)
            z.writestr('manifest.json',json.dumps(manifest))
        return sha(archive.read_bytes())
    return root,public,archive,entries,write


def test_preflight_validates_public_candidate_without_writing_site(tmp_path):
    from deploy.friends.preflight_cloud import inspect_bundle
    root,public,archive,entries,write=fixture_bundle(tmp_path)
    digest=write()
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result=inspect_bundle(archive,digest,root)
    assert result['rows']==1 and result['date']=='2026-10-20'
    assert result['status']=='preflight passed; no files changed'
    assert {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('change',['source','public','extra','hash','link','data_link','blank_name','blank_board'])
def test_preflight_refuses_changed_code_data_or_package(tmp_path,change):
    from deploy.friends.preflight_cloud import inspect_bundle
    root,public,archive,entries,write=fixture_bundle(tmp_path)
    if change=='source': (root/'src'/'friends_pages.py').write_bytes(b'changed')
    if change=='public': (public/'stocks.csv').write_bytes(b'newer data')
    if change=='extra': entries['../../private.py']=b'pass'
    if change=='link':
        (root/'data'/'friends_public').unlink()
        (root/'data'/'friends_public').symlink_to(tmp_path,target_is_directory=True)
    if change=='data_link':
        (root/'data').rename(tmp_path/'external-data')
        (root/'data').symlink_to(tmp_path/'external-data',target_is_directory=True)
    if change in ('blank_name','blank_board'):
        raw=entries['public/stocks.csv'].decode('utf-8-sig')
        entries['public/stocks.csv']=raw.replace(',测试,主板,',',,主板,' if change=='blank_name' else ',测试,,').encode('utf-8-sig')
    digest=write()
    if change=='hash': digest='0'*64
    with pytest.raises(ValueError): inspect_bundle(archive,digest,root)
