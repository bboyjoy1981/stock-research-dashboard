"""Bounded reads confined to explicitly published optional dataset files."""
import hashlib
import re
from pathlib import Path
from .public_workspace.transport import KINDS,MAX_BYTES,strict_json,decode_dataset


def load_optional_datasets(directory):
    root=Path(directory).resolve(strict=True)
    optional=root/'optional'
    if not optional.exists() and not optional.is_symlink(): return {},[]
    if optional.is_symlink() or not optional.is_dir() or optional.resolve().parent!=root:
        return {},['public_optional']
    def read(path,limit):
        if path.is_symlink() or path.resolve().parent!=optional or path.stat().st_size>limit:
            raise ValueError('Invalid public optional path or size')
        with path.open('rb') as handle: raw=handle.read(limit+1)
        if len(raw)>limit: raise ValueError('Public optional size exceeded')
        return raw
    try:
        manifest=strict_json(read(optional/'manifest.json',16_384))
        if not isinstance(manifest,dict) or set(manifest)!={'version','datasets'} or type(manifest['version']) is not int or manifest['version']!=1:
            raise ValueError('Invalid optional manifest')
        entries=manifest['datasets']
        if not isinstance(entries,dict) or set(entries)-KINDS or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in entries.values()):
            raise ValueError('Invalid optional manifest entries')
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        return {},['public_optional']
    result={}; gaps=[]
    for kind,digest in entries.items():
        try:
            raw=read(optional/(kind+'.json'),MAX_BYTES)
            if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Optional hash mismatch')
            result[kind]=decode_dataset(raw,kind)
        except (OSError,ValueError,TypeError,KeyError,UnicodeError,OverflowError):
            gaps.append(kind)
    return result,sorted(gaps)
