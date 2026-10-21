#!/usr/bin/env python3
"""Offline trial scoreboard and independent camera overlay. Does not command hardware."""
import argparse,csv,hashlib,importlib.util,json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.dont_write_bytecode=True

def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--score-script',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 basepath=a.repo/'evidence/encoder-tightening-20261021/analyze.py';base=module('baseline',basepath);scorer=module('score_native',a.score_script)
 frozen=json.loads((a.repo/'evidence/encoder-tightening-20261021/analysis-reference520/report.json').read_text())['frozen_lag']['lag_s']
 paths=[d for d in sorted(a.input.iterdir()) if d.is_dir() and (d/'report.json').exists() and 'test_parameters' in json.loads((d/'report.json').read_text())]
 paths.sort(key=lambda d:json.loads((d/'report.json').read_text())['events'][0]['host_monotonic_ns'])
 fig,axes=plt.subplots(len(paths),2,figsize=(14,2.2*len(paths)),squeeze=False);scores=[];sources=[Path(__file__),basepath,a.score_script]
 for idx,path in enumerate(paths):
  score=scorer.score(path);tr=base.load_trial(path);sources.extend(tr['sources']);st=tr['states'];h=tr['host'];mode=np.array([s['mode'] for s in st]);active=np.flatnonzero(np.isin(mode,[2,3,5,6,7,8,9,10,11]));t0=h[active[0]];t=h-t0;end=tr['report']['requested_duration_s'];q=np.array([s['theta'] for s in st]);x=np.array([s['x'] for s in st]);m=(t>=0)&(t<end);pairs=base.paired(tr,frozen);pp=[r for r in pairs if 0<=r['encoder_query_host_s']-t0<end]
  longest=max(score['balance_transitions'],key=lambda r:r['duration_s'],default=None)
  near=[]
  if longest:
   near=[r for r in pairs if longest['t_s']+2<=r['encoder_query_host_s']-t0<=longest['t_s']+longest['duration_s'] and r['mode']==3]
  rms=lambda z:float(np.sqrt(np.mean(np.square(z)))) if len(z) else None
  score['settled_independent_camera']={'samples':len(near),'image_vertical_angle_rms_deg':rms([np.degrees(r['camera_rad']) for r in near]),'camera_minus_encoder_rms_deg':rms([np.degrees(r['residual_rad']) for r in near]),'limitation':'Frozen timing proxy; raw image vertical is not certified gravity vertical. No new calibration or fusion.'}
  score['camera_rest_geometry']={label:{key:base.rest_report(tr,label).get(key) for key in ('camera_pivot_x_px','camera_pivot_y_px','camera_image_upright_rad','camera_coverage_qualified')} for label in ('before_auto_rest','after_auto_rest')}
  score['sensor_errors_delta']=tr['report']['info_after']['i2c_errors']-tr['report']['info_before']['i2c_errors'];score['camera_filters']=tr['filter_report'];score['completed_balanced']=bool(score['collector_success'] and longest and any(r['t_s']+r['duration_s']>=end-.03 for r in score['balance_transitions']))
  scores.append(score)
  ax,cart=axes[idx];ax.plot(t[m],np.abs(np.degrees(q[m])),lw=.8,label='encoder');ax.scatter([r['encoder_query_host_s']-t0 for r in pp],[abs(np.degrees(r['camera_rad'])) for r in pp],s=2,alpha=.5,label='camera geometry');ax.set_ylim(-5,185);ax.set_ylabel('Angle magnitude (deg)');ax.set_title(path.name+' | longest BAL %.2f s'%score['longest_BAL_s'],fontsize=10)
  cart.plot(t[m],x[m]*100,lw=.8,label='step-counted cart');rail=score['test_parameters']['rail']*100;cart.axhline(rail,color='r',ls='--',lw=.6);cart.axhline(-rail,color='r',ls='--',lw=.6);cart.fill_between(t[m],-35,35,where=mode[m]==3,alpha=.1,color='green',label='native BAL mode');cart.set_ylim(-35,35);cart.set_ylabel('Cart position (cm)')
  for panel in (ax,cart):panel.set_xlim(0,end);panel.grid(alpha=.2);panel.set_xlabel('Seconds after AUTO');panel.legend(loc='upper right',fontsize=7)
 fig.suptitle('Serial native AUTO trials — frozen reference 533; no encoder correction applied\nCamera framing changed before bw10 trials; image zero is not gravity vertical. Shading is native BAL mode',fontsize=12);fig.tight_layout(rect=(0,0,1,.97));fig.savefig(a.output/'trial-comparison.png',dpi=130);plt.close(fig)
 output={'frozen_lag_s':frozen,'hardware_or_calibration_accepted':False,'trials':scores,'source_hashes':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in dict.fromkeys(sources)]};(a.output/'report.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
 with (a.output/'metrics.csv').open('w',newline='') as f:
  w=csv.writer(f,lineterminator='\n');w.writerow(['trial','bw','ke','kdx','catch_v','first_capture_s','longest_BAL_s','BAL_entries','completed_balanced','new_i2c_errors','encoder_hold_RMS_deg','camera_image_vertical_RMS_deg','error'])
  for s in scores:w.writerow([s['trial'],s['test_parameters']['bw'],s['test_parameters']['ke'],s['test_parameters']['kdx'],s['test_parameters']['catch_v'],s['first_capture_s'],s['longest_BAL_s'],s['BAL_entries'],s['completed_balanced'],s['sensor_errors_delta'],(s['settled_longest_hold']['angle_deg'] or {}).get('rms'),s['settled_independent_camera']['image_vertical_angle_rms_deg'],s['collector_error']])
 print((a.output/'metrics.csv').read_text())
if __name__=='__main__':main()
