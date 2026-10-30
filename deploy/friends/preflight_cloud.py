"""Read-only release preflight. Never installs, restarts, or reads credentials."""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

MODULES={f'src/{name}.py' for name in ('friends_pages','friends_data','industry_cloud',
    'friends_cloud','friends_research','friends_trend','friends_deep')}
PAYLOAD=MODULES|{'public/stocks.csv','deploy/preflight_cloud.py'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_bundle(archive,expected_sha,root=Path('/opt/trading-friends')):
    archive,root=Path(archive),Path(root)
    if digest(archive.read_bytes())!=expected_sha:
        raise ValueError('候选包SHA256不符，停止')
    if root.is_symlink() or not root.is_dir():
        raise ValueError('站点根目录异常，停止')
    root=root.resolve()
    if any((root/name).is_symlink() or (root/name).resolve().parent!=root for name in ('data','src')):
        raise ValueError('data或src目录链接越界，停止')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or set(names)!=PAYLOAD|{'manifest.json'}:
            raise ValueError('候选包清单不符，停止')
        if any(i.file_size>10_000_000 for i in z.infolist()) or sum(i.file_size for i in z.infolist())>20_000_000:
            raise ValueError('候选包异常大小，停止')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('version')!=1 or set(manifest.get('after',{}))!=PAYLOAD:
            raise ValueError('manifest异常，停止')
        if set(manifest.get('expected_before',{}))!=MODULES|{'public/stocks.csv'}:
            raise ValueError('部署基线清单不符，停止')
        for name in PAYLOAD:
            raw=z.read(name)
            if digest(raw)!=manifest['after'][name]:
                raise ValueError(f'候选文件校验失败：{name}')
            if name.endswith('.py'):
                compile(raw.decode('utf-8'),name,'exec')
        public_link=root/'data'/'friends_public'
        public=public_link.resolve(strict=True)
        if not public_link.is_symlink() or public.parent!=(root/'data').resolve():
            raise ValueError('公开数据链接范围不符，停止')
        if public.name!='friends_public_20261020_comparison':
            raise ValueError('公开数据已切换，需重新核对，停止')
        for name,expected in manifest['expected_before'].items():
            path=public/'stocks.csv' if name=='public/stocks.csv' else root/name
            if path.is_symlink() or path.resolve().parent!=(public if name.startswith('public/') else root/'src'):
                raise ValueError(f'文件路径异常：{name}')
            if expected is None:
                if path.exists(): raise ValueError(f'目标模块已存在，需重新核对：{name}')
            elif not path.is_file() or digest(path.read_bytes())!=expected:
                raise ValueError(f'线上文件已变化，停止：{name}')
        metadata_path=public/'metadata.json'
        if metadata_path.is_symlink() or metadata_path.resolve().parent!=public:
            raise ValueError('公开元数据路径异常')
        if json.loads(metadata_path.read_text(encoding='utf-8')).get('date')!=manifest['date']:
            raise ValueError('公开交易日已变化，停止')
        reader=csv.DictReader(io.StringIO(z.read('public/stocks.csv').decode('utf-8-sig')))
        fields=['代码','名称','板块','价格','涨跌幅','成交额','行业','细分行业','流通市值','总市值']
        if reader.fieldnames!=fields:
            raise ValueError('公开字段白名单不符')
        rows=list(reader)
        if len(rows)!=manifest['rows'] or not rows or len({r['代码'] for r in rows})!=len(rows):
            raise ValueError('公开样本数量或代码异常')
        for row in rows:
            if any(not isinstance(row.get(field),str) or not row[field].strip() for field in ('名称','板块')):
                raise ValueError('公开名称或板块为空，停止')
            if len(row['代码'])!=6 or not row['代码'].isascii() or not row['代码'].isdigit():
                raise ValueError('代码异常')
            for field in fields[3:6]+fields[8:]:
                value=float(row[field])
                if not math.isfinite(value) or field!='涨跌幅' and value<0:
                    raise ValueError('公开数值异常')
    return dict(status='preflight passed; no files changed',date=manifest['date'],rows=len(rows),
        public_directory=str(public),package_sha256=expected_sha)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('sha256')
    parser.add_argument('--root',type=Path,default=Path('/opt/trading-friends'))
    args=parser.parse_args()
    try:
        print(json.dumps(inspect_bundle(args.archive,args.sha256,args.root),ensure_ascii=False))
    except (ValueError,OSError,KeyError,TypeError,SyntaxError,zipfile.BadZipFile) as error:
        raise SystemExit(f'预检停止，未修改线上文件：{error}')
