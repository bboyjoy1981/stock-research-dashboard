"""Read-only conservative local source closure for the public website candidate."""
import ast
import hashlib
from importlib.util import resolve_name
from pathlib import Path

OWNER_MODULES=frozenset(('src.storage','src.ui','src.pages_public','src.pages_review',
    'src.core_workspace','src.market_temperature','src.temperature_store',
    'src.temperature_sources','src.news_refresh','src.news_sources','src.news_snapshot',
    'src.closing_report','src.market_activity','src.reference_chain','src.forum_hot',
    'src.taoguba_hot','src.notification','src.feishu','src.overseas_temperature',
    'src.temperature_http','src.close_limits'))


def source_manifest(directory):
    """Hash only source files; never traverse data/config/secrets directories.

    All shared modules seed the closure because the registry lazily dispatches
    its fixed allowlist. Function-local imports are checked too. This is a
    conservative dependency inventory, not a runtime security proof.
    """
    root=Path(directory).resolve(strict=True)
    shared=root/'src/public_workspace'
    pending=['friends_app']
    if shared.is_symlink():
        raise ValueError('Source symlink refused')
    for path in shared.rglob('*.py'):
        relative=path.relative_to(root).with_suffix('')
        parts=list(relative.parts)
        if parts[-1]=='__init__': parts.pop()
        pending.append('.'.join(parts))
    seen=set()
    manifest={}
    while pending:
        module=pending.pop()
        if module in seen: continue
        seen.add(module)
        if any(module==bad or module.startswith(bad+'.') for bad in OWNER_MODULES):
            raise ValueError('Owner dependency: '+module)
        relative=Path(*module.split('.'))
        path=root/relative.with_suffix('.py')
        package=False
        if not path.is_file():
            path=root/relative/'__init__.py'
            package=True
        if not path.is_file():
            raise ValueError('Missing local dependency: '+module)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Source symlink refused')
        for parent in path.relative_to(root).parents:
            if (root/parent).is_symlink(): raise ValueError('Source symlink refused')
        raw=path.read_bytes()
        tree=ast.parse(raw.decode('utf-8-sig'),filename=str(path))
        manifest[path.relative_to(root).as_posix()]=hashlib.sha256(raw).hexdigest()
        package_name=module if package else module.rpartition('.')[0]
        for node in ast.walk(tree):
            dependencies=[]
            if isinstance(node,ast.Import):
                dependencies=[alias.name for alias in node.names]
            elif isinstance(node,ast.ImportFrom):
                base=resolve_name('.'*node.level+(node.module or ''),package_name) if node.level else node.module or ''
                dependencies=[base]
                for alias in node.names:
                    child=base+'.'+alias.name
                    child_path=root/Path(*child.split('.'))
                    if child_path.with_suffix('.py').is_file() or (child_path/'__init__.py').is_file():
                        dependencies.append(child)
            pending.extend(name for name in dependencies if name=='src' or name.startswith('src.'))
        parts=module.split('.')
        for depth in range(1,len(parts)):
            parent='.'.join(parts[:depth])
            if (root/Path(*parts[:depth])/'__init__.py').is_file(): pending.append(parent)
    return dict(sorted(manifest.items()))
