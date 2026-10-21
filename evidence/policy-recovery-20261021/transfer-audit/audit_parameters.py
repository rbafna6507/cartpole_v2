#!/usr/bin/env python3
"""Reconstruct preserved parameter snapshots; local files/archives only."""
import argparse,json,tarfile
from pathlib import Path
from hashlib import sha256
from cartpole_sdk.control.parameters import ControllerParameters,gains
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[3]
SOURCES={}
def local(path):
 p=ROOT/path;b=p.read_bytes();SOURCES[str(p)]=dict(sha256=sha256(b).hexdigest(),bytes=len(b));return b

def archive(path,prefix):
 raw=local(path)
 with tarfile.open(ROOT/path)as t:
  names=[m.name for m in t.getmembers()if m.isfile()and m.name.startswith(prefix+'/')]
  logs=[n for n in names if Path(n).name.startswith('rig-')and n.endswith('.jsonl')];assert len(logs)==1
  result={}
  for name in logs+([prefix+'/report.json']if prefix+'/report.json'in names else []):
   b=t.extractfile(name).read();SOURCES[str(path)+'::'+name]=dict(sha256=sha256(b).hexdigest(),bytes=len(b));result[Path(name).name]=b
 return result

def records(raw):return [json.loads(line)for line in raw.splitlines()]
def mode_snapshots(rows,base=None):
 params=dict(base or {});info=None;result=[]
 for r in sorted(rows,key=lambda r:r['host_monotonic_ns']):
  if r['type']=='parameter':params[r['name']]=r['value']
  if r['type']=='info':info=r['info']
  if r['type']=='command'and ' MODE 'in r['payload']:
   assert len(params)==41
   result.append(dict(mode_command=r,parameters=dict(params),latest_info=info))
 return result

def snapshot(name):
 root=Path('runs/policy-recovery-20261021/hardware-live')/name
 report=json.loads(local(root/'report.json'));log=next((ROOT/root).glob('rig-*.jsonl'));rows=records(local(log.relative_to(ROOT)))
 readbacks={r['name']:r['value']for r in rows if r['type']=='parameter'};assert len(readbacks)==41 and readbacks==report['parameters']
 return dict(source=str(root),parameters=readbacks,info_before=report['before_info'],info_after=report['after_info'],first_readback_ns=min(r['host_monotonic_ns']for r in rows if r['type']=='parameter'),last_readback_ns=max(r['host_monotonic_ns']for r in rows if r['type']=='parameter'))
def diffs(a,b):
 assert set(a)==set(b)
 return {k:dict(historical=a[k],comparison=b[k])for k in sorted(a)if a[k]!=b[k]}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--user-snapshot',type=Path);args=p.parse_args()
 arch=archive(Path('evidence/balance-error-20261020/live/id-followup-20261020.tar.gz'),'runs/id-followup-20261020/coupled-validation-01');report=json.loads(arch['report.json']);raw=next(b for n,b in arch.items()if n.endswith('.jsonl'));history=mode_snapshots(records(raw));assert len(history)==2 and history[0]['parameters']==history[1]['parameters']==report['parameters']
 historical=history[-1]['parameters'];auto=snapshot('inspect-01');bal=snapshot('upright-before-native-bal')
 metrics=json.loads(local(Path('evidence/balance-error-20261020/native-validation/report.json')));assert sha256(raw).hexdigest()==metrics['source_sha256']
 later=archive(Path('evidence/console-policy-20261021/live-traces-04.tar.gz'),'runs/console-policy-20261021/native-baseline-bw8-25s-01');later_report=json.loads(later['report.json']);later_rows=records(next(b for n,b in later.items()if n.endswith('.jsonl')));later_modes=mode_snapshots(later_rows);assert later_modes[0]['parameters']['bw']==8 and later_report['parameters']['bw']==10 and later_report['test_bw']==8
 current={}
 for label,base in [('native-auto-01',auto),('native-bal-01',bal)]:
  folder=Path('runs/policy-recovery-20261021/hardware-live')/label;file=next((ROOT/folder).glob('rig-*.jsonl'));rows=records(local(file.relative_to(ROOT)));assert not any(r['type']=='parameter'for r in rows)
  modes=mode_snapshots(rows,base['parameters']);assert len(modes)==1
  current[label]=dict(pretrial_snapshot=base,mode=modes[0],snapshot_to_mode_s=(modes[0]['mode_command']['host_monotonic_ns']-base['last_readback_ns'])/1e9,in_trial_parameter_reads=False,in_trial_parameter_writes=[r for r in rows if r['type']=='command'and ' PARAM 'in r['payload']],differences_from_success=diffs(historical,base['parameters']))
 result=dict(schema='cartpole-native-parameter-audit-v1',hardware_activity=False,historical_success=dict(session=report['initial_info']['sid'],initial_info=report['initial_info'],mode_snapshots=history,metrics=metrics['trials']),current=current,later_completed_bw8_trial=dict(pretrial_report_parameters=later_report['parameters'],at_mode_parameter_snapshot=later_modes[0],restored_bw=later_report['restored_bw'],semantics='25s operation completed, but longest mode3 dwell only2.024s, not a sustained balance success.'),unchanged_gain_settings={k:historical[k]for k in ['leff','pw','pz','bal_pw','pc1','pc2']},gains=dict(auto=asdict(gains(ControllerParameters(**historical))),bal=asdict(gains(ControllerParameters(**historical),upright=True))),limits=['Current native sessions contain no parameter readbacks: values are the nearest preceding full41-field readbacks and no in-session parameter commands. Unobserved actions in the intervening time cannot be disproved by these local files alone.','Reference counts are calibration/installation identity, not an independent measurement of physical vertical or physical zero drift.','bw changes observer response, not algebraic feedback coefficients; rail is governor geometry.','Native BAL intentionally selects bal_pw4.5 gains rather than AUTO pw3 despite the same saved parameter catalog.'])
 if args.user_snapshot:
  b=args.user_snapshot.read_bytes();SOURCES[str(args.user_snapshot)]=dict(sha256=sha256(b).hexdigest(),bytes=len(b));rows=records(b);params={r['name']:r['value']for r in rows if r['type']=='parameter'};assert len(params)==41
  result['user_snapshot']=dict(path=str(args.user_snapshot),parameters=params,differences_from_success=diffs(historical,params),differences_from_current_auto=diffs(auto['parameters'],params),info_records=[r for r in rows if r['type']=='info'])
 result['sources']=SOURCES;result['script_sha256']=sha256(Path(__file__).read_bytes()).hexdigest();args.output.parent.mkdir(parents=True,exist_ok=True)
 with args.output.open('x')as f:f.write(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
 print(json.dumps(dict(output=str(args.output),historical_ref=report['initial_info']['encoder_upright_raw'],current_differences={k:v['differences_from_success']for k,v in current.items()},user_differences=result.get('user_snapshot',{}).get('differences_from_current_auto'))))
if __name__=='__main__':main()
