#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3", "matplotlib>=3.8,<4"]
# ///
"""Score explicitly selected intervals from a FAILED-recording diagnostic extract.

This never recovers or admits a collection, fits coefficients, or exports a model.
The original failure remains in the output. Only a compact extract is needed;
its SHA must match the annotations produced before scoring.
"""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from compare import continuous

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('extract','intervals','freeze','output'):p.add_argument('--'+key,type=Path,required=True)
 a=p.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 z=np.load(a.extract,allow_pickle=False);meta=json.loads(z['metadata'].tobytes());ann=json.loads(a.intervals.read_text());freeze=json.loads(a.freeze.read_text())
 assert meta['completion_report']['completed'] is False
 assert ann['extract_sha256']==sha(a.extract)
 assert ann['raw_source_sha256']==meta['source_identity']['sha256']
 assert meta['all_recorded_states_healthy_homed_disabled']
 for name,digest in freeze['method_hashes'].items():assert sha(Path(__file__).parent/name)==digest,name
 c=next(x['coefficients'] for x in freeze['models'] if x['model']=='weak_coulomb');parts=[]
 for n,(lo,hi) in enumerate(ann['free_intervals_board_s'],1):
  mask=(z['t']>=lo)&(z['t']<=hi);t=z['t'][mask];q=z['raw'][mask]
  assert len(t)>500 and np.max(np.diff(t))<=.008 and t[-1]-t[0]>=2
  parts.append((t,q,('failed-prefix',f'release-{n:02}')))
 result=continuous(parts,c,.5)
 report=dict(scope='FAILED collection prefix: diagnostic only; excluded from training and formal holdout admission',accepted=False,collection_recovered=False,completion_report=meta['completion_report'],camera_report=meta['camera_report'],extract_sha256=sha(a.extract),raw_source_sha256=meta['source_identity']['sha256'],freeze_sha256=sha(a.freeze),annotation=ann,coefficients=c,continuous_after_history=result,quality_limits='No independent held-pose or camera quality admission performed on this extract; source camera failure remains a failure. Recorded states were stopped/homed/disabled. STOP confirmation is not established by a successful completion report.')
 a.output.mkdir(parents=True);(a.output/'report.json.gz').write_bytes(gzip.compress(json.dumps(report,allow_nan=False).encode(),mtime=0));summary={k:v for k,v in report.items() if k not in ('continuous_after_history','completion_report','camera_report')};summary.update(metrics=result['metrics'],episodes=len(parts));(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(5,2,figsize=(13,13),layout='constrained')
 for ax,ep in zip(axes.flat,result['episodes']):
  t=np.array(ep['t']);base=meta['baseline']['encoder']['raw_angle_rad'];ax.plot(t-t[0],np.rad2deg(np.array(ep['observed'])-base),lw=1,label='Recorded encoder');ax.plot(t-t[0],np.rad2deg(np.array(ep['predicted'])-base),lw=1,label='Frozen batch-6 model');ax.set_title(f"{ep['episode_id']}: {ep['metrics']['rms_deg']:.2f}° RMS");ax.set(xlabel='Seconds after initialization',ylabel='Degrees from initial hanging');ax.grid(alpha=.2)
 axes.flat[0].legend(fontsize=8);fig.suptitle('Failed validation-7 prefix — diagnostic only\n0.5 s initialization; no refitting; original camera failure retained');fig.savefig(a.output/'recorded-vs-predicted.png',dpi=130)
 print(json.dumps(dict(metrics=result['metrics'],episodes=len(parts),accepted=False),indent=2))
if __name__=='__main__':main()
