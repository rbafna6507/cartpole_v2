"""Stage a separate runtime; never open a serial device or modify old release."""
import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
archive=Path('/tmp/cartpole-policy-rail1mm-20261021.tar.gz')
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='3459e69a24c2157c113b187a320a5de02985288285ea2c50a59ee524025e069e'
base=Path.home()/'cartpole-v2-live/releases/id-20261021-policy-console'
release=base.with_name('id-20261021-policy-rail1mm')
before=hashlib.sha256((base/'src/cartpole_sdk/rig/neural_runner.py').read_bytes()).hexdigest()
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
python=str((base/'.venv/bin/python').resolve())
subprocess.run([uv,'sync','--locked','--extra','hardware','--extra','inference','--no-dev','--python',python],cwd=release,check=True)
assert hashlib.sha256((base/'src/cartpole_sdk/rig/neural_runner.py').read_bytes()).hexdigest()==before
print('STAGED '+json.dumps(dict(release=str(release),old_release_unchanged=True,files=len(manifest),no_serial_access=True)))
