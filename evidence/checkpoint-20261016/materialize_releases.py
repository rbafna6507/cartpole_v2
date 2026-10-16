from pathlib import Path,PurePosixPath
import tarfile,json,hashlib,os
scratch=Path('/tmp/cartpole-checkpoint-20261016');repo=Path('/Users/rbafna/projects/cartpole_v2');archive=scratch/'releases.tgz'
expected=json.loads((scratch/'capture-result.json').read_text())
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected['sha256']
index=json.loads((scratch/'local-index.json').read_text());destination=repo/'releases';assert not destination.exists()
with tarfile.open(archive,'r:gz') as tar:
 members={x.name:x for x in tar.getmembers()};assert all(x.isfile() for x in members.values())
 manifest=json.load(tar.extractfile(members['manifest.json']));verified={};planned=[]
 for release,snapshot in manifest['releases'].items():
  assert PurePosixPath(release).name==release and release not in ('.','..')
  for path,record in snapshot['files'].items():
   rel=PurePosixPath(path);assert not rel.is_absolute() and '..' not in rel.parts
   sha=record['sha256']
   if sha not in verified:
    data=Path(index[sha]).read_bytes() if sha in index else tar.extractfile(members['objects/'+sha]).read()
    assert hashlib.sha256(data).hexdigest()==sha;verified[sha]=data
   assert len(verified[sha])==record['bytes'];planned.append((release,path,record))
 for release,path,record in planned:
  p=destination/'snapshots'/release/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(verified[record['sha256']]);p.chmod(0o755 if record['executable'] else 0o644)
 (destination/'manifest-20261016.json').write_text(json.dumps(manifest,indent=2)+'\n')
 result={'releases':len(manifest['releases']),'files_verified':len(planned),'unique_contents':len(verified),'expanded_bytes':sum(r['bytes'] for _,_,r in planned),'bundle_sha256':expected['sha256']}
 (scratch/'release-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
