import gzip,hashlib,json,tarfile,io,sys
from pathlib import Path
root=Path('/home/rbafna/cartpole-v2-runs/python-id-20261016');manifest=[]
skip=set(json.loads(Path(sys.argv[1]).read_text())) if len(sys.argv)>1 else set()
with tarfile.open('/tmp/cartpole-python-id-20261016-export.tar.gz','w:gz') as out:
 for d in sorted(root.iterdir()):
  if d.name in skip or not d.is_dir() or not any((d/n).is_file() for n in ('report.json','home-report.json')):continue
  for p in sorted(d.iterdir()):
   if p.suffix not in ('.json','.jsonl'):continue
   raw=p.read_bytes();name=d.name+'/'+p.name;data=raw
   manifest.append(dict(path=name,sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),remote_path=str(p)))
   if p.suffix=='.jsonl':data=gzip.compress(raw,mtime=0);name+='.gz'
   item=tarfile.TarInfo(name);item.size=len(data);out.addfile(item,io.BytesIO(data))
 data=json.dumps(manifest,indent=2).encode();item=tarfile.TarInfo('new-manifest.json' if skip else 'manifest.json');item.size=len(data);out.addfile(item,io.BytesIO(data))
print(json.dumps(dict(files=len(manifest),bytes=Path('/tmp/cartpole-python-id-20261016-export.tar.gz').stat().st_size)))
