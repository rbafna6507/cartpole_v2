"""Add a separate release; never open serial, alter firmware or stop processes."""
import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
archive=Path('/tmp/cartpole-policy-swingup-20261021.tar.gz')
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='2a677cc280eead478f2377cded4c5c7d02cacc6a88578af521ce2fa012eb671b'
base=Path.home()/'cartpole-v2-live/releases/id-20261021-policy-rail1mm'
release=base.with_name('id-20261021-policy-swingup')
changed=('src/cartpole_sdk/learning/balance_hardware.py','src/cartpole_sdk/rig/console_policy.py','src/cartpole_sdk/rig/console.py')
before={name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in changed}
release.mkdir(exist_ok=False)
for name in ('src','scripts','docs'):
    shutil.copytree(base/name,release/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in ('pyproject.toml','uv.lock','README.md'):shutil.copy2(base/name,release/name)
with tarfile.open(archive) as package:
    for entry in package.getmembers():
        path=Path(entry.name)
        if not entry.isfile() or path.is_absolute() or '..' in path.parts:raise ValueError('unsafe member')
    package.extractall(release,filter='data')
manifest=json.loads((release/'deployment-files.json').read_text())
for name,digest in manifest.items():assert hashlib.sha256((release/name).read_bytes()).hexdigest()==digest
uv=shutil.which('uv') or str(Path.home()/'.local/bin/uv')
subprocess.run([uv,'sync','--locked','--extra','hardware','--extra','inference','--no-dev',
    '--python',str((base/'.venv/bin/python').resolve())],cwd=release,check=True)
for name,digest in before.items():assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest
subprocess.run([str(release/'.venv/bin/python'),'verify-policy-swingup.py',
    '--output','jetson-verification.json'],cwd=release,check=True)
print(json.dumps(dict(release=str(release),old_release_unchanged=True,files=len(manifest),no_serial_access=True)))
