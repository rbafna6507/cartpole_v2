#!/usr/bin/env python3
"""Compare completed hardware starts; never connects to the rig or fits a model."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
CASES = (
    ('balance47-run10-camera04', 'Original actor: 7.22 s hold / timeout'),
    ('centered-run25-camera05', 'Centered actor: growing oscillation'),
    ('balance47-run25-camera06', 'Original actor: 25 s run / balance lost'),
)

def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))

def column(rows, key):
    return np.asarray([float(r[key]) for r in rows], dtype=float)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    fig,axes=plt.subplots(5,3,figsize=(16,12),sharex=True,layout='constrained')
    report={'schema':'cartpole-observed-startup-comparison-v1', 'source_sha256':digest(Path(__file__)), 'cases':[],
      'limits':['Post-hoc descriptive comparison, not a randomized causal experiment.',
                'Reference, pose and scheduler differ between trials; no single cause is isolated.',
                'Cart coordinates count steps and speed is commanded, not independent physical truth.',
                'Camera is image angle with exposure/processing lag and unvalidated vertical/cart calibration.',
                'The first measured >5 degree event is not proof of equal true physical angle.',
                'No physical fitting, training, parameter update or hardware access.']}
    for index,(name,label) in enumerate(CASES):
        folder=HERE/name
        files=[folder/n for n in ('analysis.json','telemetry.csv','actions.csv','camera-alignment.csv')]
        summary=json.loads(files[0].read_text())
        rows=read_csv(files[1]); actions=read_csv(files[2]); camera=read_csv(files[3])
        t=column(rows,'board_t_s'); early=t<=1.5
        axes[0,index].plot(t[early],column(rows,'theta_encoder_deg')[early],label='Encoder')
        ct=column(camera,'relative_active_s'); ce=ct<=1.5
        axes[0,index].plot(ct[ce],np.rad2deg(column(camera,'theta_camera_rad')[ce]),label='Camera image angle',alpha=.75)
        axes[0,index].axhline(5,color='grey',ls=':',lw=.7)
        axes[0,index].axhline(-5,color='grey',ls=':',lw=.7)
        axes[0,index].set_title(label,fontsize=10)
        axes[1,index].plot(t[early],column(rows,'observer_rate_rad_s')[early],color='#a03b22')
        axes[2,index].plot(t[early],1000*column(rows,'x_step_estimate_m')[early],color='#497542')
        axes[3,index].plot(t[early],column(rows,'accepted_demand_m_s2')[early],label='Demand')
        axes[3,index].plot(t[early],column(rows,'governed_acceleration_m_s2')[early],label='Governed',alpha=.8)
        at=column(actions,'board_t_s'); ae=at<=1.5
        axes[4,index].plot(at[ae],column(actions,'receipt_to_command_record_ms')[ae],color='#6d52a1')
        axes[4,index].set_xlabel('Seconds since first active telemetry')
        bins=[]
        for lo,hi in ((0,.25),(.25,.5),(.5,.75),(.75,1.0)):
            mask=(t>=lo-1e-8)&(t<hi-1e-8)
            bins.append({'interval_s':[lo,hi], 'samples':int(sum(mask)),
              'max_abs_encoder_deg':float(np.max(np.abs(column(rows,'theta_encoder_deg')[mask]))),
              'demand_rms_m_s2':float(np.sqrt(np.mean(column(rows,'accepted_demand_m_s2')[mask]**2)))})
        initial=[{key:row[key] for key in ('board_t_s','theta_encoder_deg','observer_rate_rad_s','x_step_estimate_m','accepted_demand_m_s2','governed_acceleration_m_s2')} for row in rows[:4]]
        report['cases'].append({'name':name,'input_sha256':{str(p.relative_to(HERE)):digest(p) for p in files},
          'reference':summary['calibration']['saved_reference_counts'], 'first_samples':initial,
          'first_second_quarters':bins, 'first_measured_over_5deg_s':summary['first_abs_encoder_over_5deg_s'],
          'first_rail_braking_s':summary['first_rail_braking_s'], 'active_span_s':summary['active_span_s'],
          'requests':summary['requests']})
    for ax in axes.flat:
        ax.grid(alpha=.2); ax.set_xlim(0,1.5)
    for ax,label in zip(axes[:,0],('Angle (deg)','Observer rate (rad/s)','Counted cart (mm)','Acceleration (m/s²)','Receipt to command record (ms)')):
        ax.set_ylabel(label)
    axes[0,0].legend(fontsize=8); axes[3,0].legend(fontsize=8)
    fig.suptitle('Startup response varies sharply; longer control uptime does not establish balance',fontsize=15)
    fig.savefig(args.output/'startup-comparison.png',dpi=160)
    report['plot_sha256']=digest(args.output/'startup-comparison.png')
    (args.output/'analysis.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2,allow_nan=False))

if __name__=='__main__':main()
