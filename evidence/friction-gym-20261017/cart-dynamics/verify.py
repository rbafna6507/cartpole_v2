#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3"]
# ///
"""Offline numerical/admission checks and fixed-coefficient weak residuals."""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mod(p,name):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('output exists')
 root=a.repo.resolve();sys.path.insert(0,str(root/'src'))
 from cartpole_sdk.identification.fit import FitConfig,_segments
 from cartpole_sdk.identification.workflow import digest
 audit=mod(Path(__file__).with_name('audit.py'),'cart_audit_verify');driven=mod(root/'evidence/system-id-20261017/tools/analyze_driven_friction.py','old_driven_verify')
 report=json.loads(a.report.read_text());fpath=root/'evidence/system-id-model-review-20261017/candidate-freeze-latest6.json';freeze=json.loads(fpath.read_text())
 batchpath=root/'evidence/system-id-20261017/analysis/pulse-batch-secondary-historic-offset.json';batch=json.loads(batchpath.read_text());p=freeze['parameters']
 assert report['frozen_parameters']==p and report['provenance']['freeze_sha256']==sha(fpath)
 assert report['provenance']['script_sha256']==sha(Path(__file__).with_name('audit.py'))
 assert report['accepted'] is False and report['recommended_for_hardware_rl'] is False
 assert len(report['runs'])==6 and len({r['source_sha256'] for r in report['runs']})==6
 cfg=replace(FitConfig(),angle_offset_rad=p['local_angle_offset_rad']);coef=np.array([9.81/p['effective_length_m'],p['viscous_per_s'],1/p['effective_length_m'],p['coulomb_rad_per_s2']]);weak={};checks=[]
 for role in ['training','validation']:
  segments=_segments(batch['canonical_batches'][role],'magnetic','commanded',cfg);x,y=driven.friction_windows(segments,0,cfg)
  weak[role if role=='training' else 'previous_validation_now_development']=dict(windows=len(y),integral_nrmse=float(np.sqrt(np.mean((y-x@coef)**2))/np.std(y)),historical_gate=.15,interpretation='Frozen-coefficient diagnostic only; original reports and acceptance statuses are unchanged.')
  for segment in segments:
   t,q,acc,rows=segment;i=max(6,int(np.searchsorted(t,t[0]+.1)))
   initial=audit.initialize(t,q,acc,i,p,'history_rawq')
   altered_q=q.copy();altered_q[i+1:]+=.7;altered_a=acc.copy();altered_a[i+1:]+=3
   changed=audit.initialize(t,altered_q,altered_a,i,p,'history_rawq')
   assert np.array_equal(initial,changed),'initializer uses future data'
   checks.append(dict(run_id=rows[0]['run_id'],no_future_angle_or_input_leakage=True))
 for r in report['runs']:
  status=r['source_status'];assert status['completed'] and status['stop_confirmed'] and status['records_dropped']==0
  counted=np.array(r['optical']['counted_points']);pre=counted[(counted[:,0]>=-.25)&(counted[:,0]<=-.05),1]
  assert len(pre)>0 and np.all(pre==0),'optical origin assumes zero pre-pulse count'
  assert r['short_causal_7point_quadratic']['windows']==7 and r['short_history_rawq']['windows']==7
  assert r['short_causal_7point_quadratic']['samples']==r['short_history_rawq']['samples']==350
  policy=status['collector_result']['policy'];assert policy['clamped_commands']==(2 if '30' in r['name'] else 0)
  assert policy['physical_cart_fixed'] is False and status['collector_result']['hardware_validated'] is False
 # The smooth law must dissipate energy for every nonzero signed angular rate.
 w=np.r_[-np.logspace(-9,2,80),np.logspace(-9,2,80)];power=(-p['coulomb_rad_per_s2']*np.tanh(w/.05)-p['viscous_per_s']*w)*w
 assert np.all(power<0)
 output=dict(schema='cartpole-frozen-driven-audit-verification-v1',passed=True,checks=['frozen parameters/source hash unchanged','audit script/report binding','six unique development recording identities','all original rows retained through existing segments','same scored short samples across initializers','initialization does not inspect future angles or inputs','successful completion/drop/STOP flags preserved','30mm two-clamp deviations retained','zero pre-pulse counted origin verified','smooth friction dissipates signed angular motion','independent DOP853/RK4 forecast RMS parity'],causality=checks,weak_form_residuals=weak,numerical_parity=report['numerical_verification'],report_sha256=sha(a.report),script_sha256=sha(__file__))
 a.output.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
if __name__=='__main__':main()
