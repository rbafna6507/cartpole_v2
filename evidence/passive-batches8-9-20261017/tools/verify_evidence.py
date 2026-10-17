#!/usr/bin/env python3
"""Verify preserved originals, independent sources and frozen analysis outputs."""
import argparse,ast,gzip,hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(p.read_text())
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--xz',default=shutil.which('xz') or 'xz',help='xz executable (default: PATH)')
p.add_argument('--archives-only',action='store_true',help='Verify committed archives without requiring ignored local extracted copies')
a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
prior=ROOT.parent/'system-id-model-review-20261017';freeze=read(prior/'candidate-freeze-latest6.json');freeze_sha=digest((prior/'candidate-freeze-latest6.json').read_bytes());assert freeze_sha==read(ROOT/'freeze-verification.json')['freeze_sha256']
for name,h in freeze['method_hashes'].items():assert digest((prior/'tools'/name).read_bytes())==h,name
identities=[];seen=set();files_checked=[];counts={}
for label in ['training8','validation8','training9','validation9']:
 directory=ROOT/label;manifest=read(directory/'manifest.json');archive=directory/'original.tar.xz';assert digest(archive.read_bytes())==manifest['archive_sha256'];assert archive.stat().st_size==manifest['archive_bytes']
 checked=set()
 with subprocess.Popen([a.xz,'-dc',str(archive)],stdout=subprocess.PIPE) as proc:
  with tarfile.open(fileobj=proc.stdout,mode='r|') as tar:
   for member in tar:
    assert member.isfile() and member.name in manifest['archive_members'] and member.name not in checked
    raw=tar.extractfile(member).read();actual=dict(bytes=len(raw),sha256=digest(raw));assert actual==manifest['archive_members'][member.name]
    if not a.archives_only:
     local=Path(manifest['extraction_root'])/member.name;assert digest(local.read_bytes())==actual['sha256']
    checked.add(member.name);files_checked.append(dict(recording=label,member=member.name,**actual))
  assert proc.wait()==0
 assert checked==set(manifest['archive_members'])
 assert manifest['completed'] is True and manifest['stop_confirmed'] is True and manifest['records_dropped']==0 and manifest['source_unchanged_across_transfer'] is True
 raw_sha=manifest['raw_sha256'];assert raw_sha not in seen and raw_sha not in freeze['development_source_sha256'];seen.add(raw_sha)
 annotations=read(directory/'annotations.json');assert annotations['selected_before_scoring'] is True and annotations['source_sha256']==raw_sha
 report=json.loads(gzip.decompress((directory/'model-check/report.json.gz').read_bytes()));assert report['freeze_sha256']==freeze_sha and report['accepted'] is False and report['exported'] is False
 identity=report['source_identity'];assert identity['sha256']==raw_sha and identity['annotations_sha256']==digest((directory/'annotations.json').read_bytes());assert identity['session']==manifest['session']
 expected={e['episode_id'] for e in annotations['episodes']};assert {e['episode_id'] for e in report['camera_quality']['episodes']}==expected
 assert len(report['results'])==len(freeze['models'])
 for m,f in zip(report['results'],freeze['models']):
  assert all(m[k]==f[k] for k in ['model','initializer','coefficients'])
  assert {e['episode_id'] for e in m['metrics']['episodes']}==expected and not m['metrics']['skipped_segments']
  assert {c['warmup_s'] for c in m['metrics']['continuous_after_history']}==set(freeze['continuous_initialization_s'])
 assert len({m['metrics']['short']['samples'] for m in report['results']})==1
 for name,key in [('raw-preview.png','raw_preview_sha256'),('raw-release-onsets.png','raw_onsets_sha256')]:assert digest((directory/name).read_bytes())==annotations[key]
 identities.append(dict(label=label,raw_sha256=raw_sha,session=manifest['session']['session_id'],annotations_sha256=identity['annotations_sha256'],camera_passed=report['camera_quality']['passed'],all_poses_verified=report['camera_quality']['all_release_poses_verified']))
 counts[label]=len(expected)
for name,labels,scored9 in [('batch8-summary.json',{'training8','validation8'},False),('batch9-summary.json',{'training9','validation9'},True),('all4-summary.json',{'training8','validation8','training9','validation9'},True)]:
 s=read(ROOT/name);assert {r['label'] for r in s['recordings']}==labels and s['batch9_scored'] is scored9 and s['refitted'] is False and s['accepted'] is False
 assert s['freeze_sha256']==freeze_sha
 for m in s['combined']:
  inputs=[next(x for x in r['models'] if x['model']==m['model'] and x['initializer']==m['initializer']) for r in s['recordings']]
  assert sum(x['short']['samples'] for x in inputs)==m['short']['samples']
  for c in m['continuous_after_history']:assert sum(next(h['metrics']['samples'] for h in x['continuous_after_history'] if h['warmup_s']==c['warmup_s']) for x in inputs)==c['metrics']['samples']
for p in (ROOT/'tools').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
out=dict(freeze_sha256=freeze_sha,frozen_model_and_methods_unchanged=True,original_archive_files_verified=files_checked,local_copies_verified=not a.archives_only,distinct_sources_excluded_from_development=True,source_identities=identities,all_selected_releases_scored=counts,no_skipped_segments=True,both_declared_initialization_histories_preserved=True,all_model_comparisons_use_equal_samples=True,summary_sample_counts_verified=True,all_helper_scripts_parse=True,accepted=False,refitted=False)
a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['original_archive_files_verified','source_identities']},indent=2))
