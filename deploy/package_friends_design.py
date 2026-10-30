"""Build a three-entry guest UI candidate; never include secrets or snapshots."""
from pathlib import Path
import ast
import hashlib
import json
import tomllib
import zipfile


def build(output_directory):
    root = Path(__file__).resolve().parents[1]
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        'src/friends_pages.py': (root / 'src/friends_pages.py').read_bytes(),
        '.streamlit/config.toml': (root / 'deploy/friends/config.toml').read_bytes(),
    }
    ast.parse(files['src/friends_pages.py'].decode('utf-8'))
    tomllib.loads(files['.streamlit/config.toml'].decode('utf-8'))
    sha = lambda content: hashlib.sha256(content).hexdigest()
    with zipfile.ZipFile(root / 'deploy/trading-friends-code-20261014.zip') as baseline:
        before = sha(baseline.read('src/friends_pages.py'))
    manifest = {
        'version': 1, 'purpose': 'guest UI only; no auth or data migration',
        'expected_before': {'src/friends_pages.py': before, '.streamlit/config.toml': None},
        'after': {name: sha(content) for name, content in files.items()},
        'config_policy': 'Install only if target config is absent; otherwise stop for review.',
    }
    target = output / 'trading-friends-design-20261020-r2.zip'
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
    with zipfile.ZipFile(target) as archive:
        assert len(archive.namelist()) == 3
        assert set(archive.namelist()) == {*files, 'manifest.json'}
        assert all(sha(archive.read(name)) == manifest['after'][name] for name in files)
    return {'package': str(target), 'sha256': sha(target.read_bytes()), 'manifest': manifest}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-directory', required=True)
    print(json.dumps(build(parser.parse_args().output_directory), ensure_ascii=False, indent=2))
