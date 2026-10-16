"""Read-only deployment capture; writes a deduplicated transfer bundle in /tmp."""
from pathlib import Path
import os,io,json,hashlib,tarfile,datetime
base=Path('/home/rbafna/cartpole-v2-live')
roots={'legacy-current':base/'current',**{p.name:p for p in sorted((base/'releases').iterdir()) if p.is_dir()},'legacy-firmware':base/'firmware'}
excluded={'.venv','.venv-vision','__pycache__','.pytest_cache','.git','runs','logs','reports','build','dist','node_modules'}
known=set(json.loads(Path('/tmp/cartpole-checkpoint-known-hashes.json').read_text()));blobs={}
manifest={'schema_version':1,'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'active_operator_release':'platform-20261015-v6-tunable','excluded_directories':sorted(excluded),'excluded_other':'*.egg-info directories, *.pyc/*.pyo, .DS_Store and AppleDouble ._* files','releases':{}}
for name,root in roots.items():
 files={}
 for here,dirs,names in os.walk(root):
  dirs[:]=sorted(d for d in dirs if d not in excluded and not d.endswith('.egg-info'))
  for filename in sorted(names):
   p=Path(here)/filename
   if filename.endswith(('.pyc','.pyo')) or filename.startswith('._') or filename=='.DS_Store':continue
   if p.is_symlink():raise RuntimeError(f'unexpected symlink: {p}')
   data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();rel=p.relative_to(root).as_posix()
   files[rel]={'sha256':sha,'bytes':len(data),'executable':bool(p.stat().st_mode&0o111)}
   if sha not in known:blobs.setdefault(sha,data)
 manifest['releases'][name]={'source_directory':str(root),'files':files}
output=Path('/tmp/cartpole-release-checkpoint-20261016.tgz')
with tarfile.open(output,'w:gz',compresslevel=9) as tar:
 entries={'manifest.json':(json.dumps(manifest,indent=2)+'\n').encode(),**{'objects/'+k:v for k,v in blobs.items()}}
 for name,data in entries.items():
  info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;tar.addfile(info,io.BytesIO(data))
print(json.dumps({'bundle':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'release_count':len(manifest['releases']),'files':sum(len(x['files']) for x in manifest['releases'].values()),'downloaded_unique_blobs':len(blobs),'downloaded_bytes':sum(map(len,blobs.values()))}))
