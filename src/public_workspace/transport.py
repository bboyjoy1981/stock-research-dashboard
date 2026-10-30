"""Pure, versioned scalar transport for already audited public datasets."""
import json
import gzip
import io
from datetime import datetime,date
import pandas as pd
from .contracts import PublicDataset

KINDS=frozenset(('history','index_history','concepts','capital_replay','news','daily_history','temperature','close_limits'))
MAX_BYTES=10_000_000
MAX_EXPANDED_BYTES=100_000_000


def strict_json(raw):
    def pairs(values):
        result={}
        for key,value in values:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    def invalid(value): raise ValueError('Nonfinite JSON constant')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def encode_dataset(dataset):
    # Revalidate mutable frame contents before any output is created.
    clean=PublicDataset(dataset.kind,dataset.frame,dict(dataset.metadata))
    _published_source(clean)
    frame=clean.frame.astype(object).where(pd.notna(clean.frame),None)
    def scalar(value):
        if isinstance(value,(datetime,date)): return value.isoformat()
        raise ValueError('Unsupported public scalar')
    value=dict(version=1,kind=clean.kind,metadata=dict(clean.metadata),columns=list(frame.columns),rows=frame.values.tolist())
    raw=json.dumps(value,ensure_ascii=False,allow_nan=False,default=scalar,separators=(',',':')).encode('utf-8')
    if len(raw)>MAX_EXPANDED_BYTES: raise ValueError('Public dataset exceeds expanded size limit')
    if len(raw)>MAX_BYTES: raw=gzip.compress(raw,mtime=0)
    if len(raw)>MAX_BYTES: raise ValueError('Public dataset exceeds stored size limit')
    return raw


def decode_dataset(raw,expected_kind):
    if expected_kind not in KINDS or not isinstance(raw,bytes) or len(raw)>MAX_BYTES:
        raise ValueError('Invalid public dataset transport')
    if raw.startswith(b'\x1f\x8b'):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as handle:
                raw=handle.read(MAX_EXPANDED_BYTES+1)
        except (OSError,EOFError) as error:
            raise ValueError('Invalid compressed public dataset') from error
        if len(raw)>MAX_EXPANDED_BYTES: raise ValueError('Expanded public dataset exceeds size limit')
    value=strict_json(raw)
    if not isinstance(value,dict) or set(value)!={'version','kind','metadata','columns','rows'}:
        raise ValueError('Invalid public dataset envelope')
    if type(value['version']) is not int or value['version']!=1 or value['kind']!=expected_kind:
        raise ValueError('Public dataset version or kind mismatch')
    columns=value['columns']; rows=value['rows']
    if not isinstance(columns,list) or any(not isinstance(c,str) for c in columns) or len(set(columns))!=len(columns):
        raise ValueError('Invalid public columns')
    if not isinstance(rows,list) or any(not isinstance(row,list) or len(row)!=len(columns) for row in rows):
        raise ValueError('Invalid public rows')
    dataset=PublicDataset(expected_kind,pd.DataFrame(rows,columns=columns),value['metadata'])
    _published_source(dataset)
    return dataset


def _published_source(dataset):
    source=dataset.metadata['source']
    if '演示' in source or 'demo' in source.lower():
        raise ValueError('Published demo fallback forbidden')
