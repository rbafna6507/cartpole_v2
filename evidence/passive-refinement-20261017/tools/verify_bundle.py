#!/usr/bin/env python3
"""Read-only verification of the preserved passive-refinement evidence bundle."""
import argparse,datetime,gzip,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parents[1]
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,default=HERE);parser.add_argument('--output',type=Path);args=parser.parse_args();root=args.evidence
    v=read(root/'verification.json');f=read(root/'candidate-freeze.json');s=read(root/'summary.json');rows=read(root/'per-release.json')
    checked=[]
    for name,digest in v['outputs'].items():assert sha(root/name)==digest,name;checked.append(name)
    for name,digest in v['tool_hashes'].items():assert sha(root/'tools'/name)==digest,name
    for name,digest in f['method_hashes'].items():assert sha(ROOT/name)==digest,name
    assert sha(root/'training.json.gz')==f['training_report_sha256']
    assert sha(ROOT/f['baseline']['freeze_path'])==f['baseline']['freeze_sha256']
    assert sha(root/'candidate-freeze.json')==s['freeze_sha256']
    assert {x['label'] for x in f['training_sources']}=={'training6','development6','training8','training9'}
    for x in f['training_sources']:
        assert sha(ROOT/x['annotations'])==x['annotations_sha256']
        assert sha(ROOT/x['archive'])==x['archive_sha256']
    assert len(rows)==66 and len({(x['label'],x['episode_id']) for x in rows})==66
    for group,labels in [('regression_pooled',{'validation8','validation9'}),('latest4_pooled',{'training8','training9','validation8','validation9'})]:
        selected=[r for r in rows if r['label'] in labels]
        for model in ['baseline','candidate']:
            for key in ['short','.25','.5']:
                points=sum(r[model][key]['samples'] for r in selected)
                rms=math.sqrt(sum(r[model][key]['rms_deg']**2*r[model][key]['samples'] for r in selected)/points)
                m=s[group][model][key]
                assert points==m['samples'] and abs(rms-m['rms_deg'])<1e-10
    partial=next(r for r in rows if r['label']=='training6' and r['episode_id']=='release-09')
    assert partial['short_windows']=={'baseline':2,'candidate':2}
    assert partial['short_coverage_pass']=={'baseline':False,'candidate':False}
    assert all(r['short_numeric_pass']=={'baseline':True,'candidate':True} for r in rows)
    assert s['recommendation']=='retain frozen baseline'
    assert s['regression_checks']['primary_improves_at_least_5pct'] is False
    assert s['quality']['latest4']=={'releases':47,'camera_pass':43,'pose_pass':38}
    result=dict(passed=True,checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),checked_output_files=len(checked),checked_tools=len(v['tool_hashes']),source_split_verified=True,pooled_rms_recomputed_from_all_releases=True,all_releases_retained=66,known_coverage_failure_retained=True,baseline_unchanged=True,freeze_sha256=sha(root/'candidate-freeze.json'),verification_sha256=sha(root/'verification.json'))
    if args.output:
        if args.output.exists():raise FileExistsError(args.output)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
