#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3"]
# ///
"""Evaluate frozen experimental coefficients on a new recording, without refitting."""
import argparse,gzip,hashlib,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from cartpole_sdk.identification import workflow,passive,release_review
from dynamics import score
from compare import continuous

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    f=workflow.read_json(a.freeze)
    for name,digest in f['method_hashes'].items():
        if sha(Path(__file__).parent/name)!=digest:raise ValueError('frozen method changed: '+name)
    eps,identity=workflow.passive_episodes(str(a.source),a.annotations)
    if identity['sha256'] in f['development_source_sha256']:raise ValueError('new recording required; development recording cannot be a fresh check')
    quality=release_review.analyze_releases(str(a.source),a.annotations);parts=passive.segments(eps,dict(passive.DEFAULT_GATES,window_s=.35));results=[]
    for model in f['models']:
        result=score(parts,model['coefficients'],model['initializer'],trace=True)
        result['continuous_after_history']=[continuous(parts,model['coefficients'],w) for w in f['continuous_initialization_s']]
        gate=lambda m:math.radians(m['rms_deg'])<=.08 and math.radians(m['p95_deg'])<=.15
        results.append(dict(**model,metrics=result,short_numeric_gates_pass=gate(result['short']) and all(e['short'] and gate(e['short']) for e in result['episodes']),short_coverage_gates_pass=all(len(e['initial_states'])>=passive.DEFAULT_GATES['min_prediction_windows'] for e in result['episodes'])))
    report=dict(scope='Frozen experimental check, not production model admission',accepted=False,exported=False,source_identity=identity,camera_quality=quality,freeze_sha256=sha(a.freeze),results=results)
    a.output.mkdir(parents=True);(a.output/'report.json.gz').write_bytes(gzip.compress(json.dumps(report,indent=2,allow_nan=False).encode(),mtime=0))
    summary=dict(source_identity=identity,accepted=False,model_exported=False,camera_passed=quality['passed'],poses_verified=quality['all_release_poses_verified'],camera_reasons=quality['reasons'],freeze_sha256=sha(a.freeze),results=[dict(model=r['model'],initializer=r['initializer'],short=r['metrics']['short'],short_numeric_gates_pass=r['short_numeric_gates_pass'],short_coverage_gates_pass=r['short_coverage_gates_pass'],continuous_after_history=[dict(warmup_s=c['warmup_s'],metrics=c['metrics']) for c in r['metrics']['continuous_after_history']]) for r in results]);workflow.write_json(a.output/'summary.json',summary);print(json.dumps(summary['results'],indent=2))
if __name__=='__main__':main()
