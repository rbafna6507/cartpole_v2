#!/usr/bin/env python3
"""Reproducible offline overview of native AUTO only, no acceptance promotion.

python campaign_overview.py --old OLD520/report.json --new NEW533/report.json
                            --output NEW_DIRECTORY
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

import numpy as np

spec=importlib.util.spec_from_file_location('encoder_base',Path(__file__).with_name('analyze.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def metric_row(s):
    windows=s.get('postcapture_windows',{});w=windows.get('after_2s',{})
    def get(section,key):return w.get(section,{}).get(key)
    p=s.get('parameters') or {}
    return dict(trial=s['trial'],reference_counts=s['reference_counts'],bw=p.get('bw'),
        native_auto_observed_s=s['native']['auto_mode_duration']['total_s'],
        first_BAL_s=s['native']['time_to_first_balance_s'],native_BAL_total_observed_s=s['native']['balance_mode_duration']['total_s'],
        longest_BAL_observed_s=s['native']['balance_mode_duration']['longest_continuous_s'],
        max_abs_AUTO_step_cart_m=s['telemetry']['max_abs_cart_auto_step_m'],
        after2_encoder_rms_deg=get('encoder_angle_deg','rms'),after2_step_cart_mean_m=get('cart_step_position_m','mean'),
        after2_step_cart_rms_m=get('cart_step_position_m','rms'),after2_step_cart_max_abs_m=get('cart_step_position_m','max_abs'),
        after2_step_cart_slope_m_s=get('cart_step_position_m','slope_per_s'),
        first5_after2_step_cart_mean_m=windows.get('first_5s_after_2s',{}).get('cart_step_position_m',{}).get('mean'),
        last5_step_cart_mean_m=windows.get('last_5s',{}).get('cart_step_position_m',{}).get('mean'),
        after2_demanded_acceleration_rms_m_s2=get('demanded_acceleration_m_s2','rms'),
        after2_governed_acceleration_rms_m_s2=get('commanded_acceleration_m_s2','rms'),
        after2_demand_total_variation_rate_m_s3=get('demanded_acceleration_m_s2','total_variation_per_s'),
        after2_governed_acceleration_difference_rate_rms_m_s3=get('commanded_acceleration_m_s2','difference_rate_rms'),
        after2_camera_upright_rms_deg=get('camera_angle_from_user_upright_deg','rms_deg'),
        after2_camera_encoder_rms_deg=get('camera_minus_encoder_deg','rms_deg'),
        after2_camera_valid_fraction=get('camera_coverage','valid_fraction'),
        camera_upright_anchor_confirmed=s.get('upright_anchor_same_view_confirmed',False),
        timeline_group='original520' if s['reference_counts']==520 else 'after_user_handling' if s['trial'] in ('ref533-bw6-auto25-02','ref533-bw8-home-auto25-03') else 'before_user_handling',
        hardware_accepted=False)


def contiguous_spans(t,mask):
    spans=[];start=None
    for i in range(len(t)):
        if mask[i]:
            if start is None:start=i
            elif t[i]-t[i-1]>base.GAP_S+1e-9:
                spans.append((t[start],t[i-1]));start=i
        elif start is not None:spans.append((t[start],t[i-1]));start=None
    if start is not None:spans.append((t[start],t[-1]))
    return spans


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv)
    old=base.read_json(a.old);new=base.read_json(a.new)
    summaries=[s for s in old['trials'] if s['native']['auto_mode_duration']['sample_count']>0]
    summaries += [s for s in new['trials'] if s.get('native_command')=='AUTO']
    a.output.mkdir(parents=True,exist_ok=False)
    trials=[base.load_trial(Path(s['source'])) for s in summaries]
    sources=[a.old,a.new,Path(__file__),Path(__file__).with_name('analyze.py')]
    for t in trials:sources.extend(t['sources'])
    rows=[metric_row(s) for s in summaries]
    with (a.output/'metrics.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    caution='Native mode3 BAL is controller state. Encoder/step evidence is separate from camera/physical truth, and no learned-policy or hardware acceptance is promoted. New upright reference520→533 preceded successful533 BW8 trials without gain changes; camera moved then. Two initial533 BW8 trials sustained BAL; after user handling, one BW6 trial and the final BW8/fullHOME trial did not. Bandwidth is not isolated as the causal factor. All duration metrics require both observed endpoints.'
    (a.output/'metrics.json').write_text(json.dumps(dict(caution=caution,rows=rows,source_hashes=[dict(path=str(f.resolve()),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sources]),indent=2,allow_nan=False)+'\n')
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'encoder-tightening-matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(len(trials),2,figsize=(13,2.1*len(trials)+1.2),sharex=True,layout='constrained',squeeze=False)
    for axrow,t,s,row in zip(axes,trials,summaries,rows):
        mode=np.array([x['mode'] for x in t['states']]);selected=np.isin(mode,base.AUTO_MODES)
        tt=t['host'][selected];ss=[x for x,k in zip(t['states'],selected) if k];mm=mode[selected];tt=tt-tt[0]
        angle=np.degrees([x['theta'] for x in ss]);cart=100*np.array([x['x'] for x in ss])
        xx=[];yy=[];zz=[]
        for i in range(len(tt)):
            if i and tt[i]-tt[i-1]>base.GAP_S+1e-9:xx.append(np.nan);yy.append(np.nan);zz.append(np.nan)
            xx.append(tt[i]);yy.append(np.nan if i and abs(angle[i]-angle[i-1])>180 else angle[i]);zz.append(cart[i])
        axrow[0].plot(xx,yy,color='#376eb7',lw=.65);axrow[1].plot(xx,zz,color='#bd7337',lw=.75)
        for lo,hi in contiguous_spans(tt,mm==3):
            for ax in axrow:ax.axvspan(lo,hi,color='#59a56a',alpha=.2)
        for ax in axrow:
            ax.grid(alpha=.2);ax.set_xlim(0,25);ax.axhline(0,color='black',lw=.5,alpha=.4)
        axrow[0].set_ylim(-20,20);axrow[0].set_ylabel('Encoder (deg)')
        axrow[1].set_ylim(-32,32);axrow[1].set_ylabel('Counted cart position (cm)')
        label=s['trial']+f" | ref{s['reference_counts']} / bw{row['bw']:g}"
        axrow[0].set_title(label,loc='left',fontsize=9)
        catch=row['first_BAL_s'];catch_text='none' if catch is None else f'{catch:.3f}s'
        axrow[1].set_title(f'First BAL: {catch_text}; longest observed BAL: {row["longest_BAL_observed_s"]:.3f}s',loc='left',fontsize=9)
    for ax in axes[-1]:ax.set_xlabel('Seconds from first native AUTO state')
    fig.suptitle('Native AUTO campaign | green: native BAL | angle view clipped at±20°\nTwo sustained holds after upright calibration; subsequent runs did not repeat them.',fontsize=11)
    fig.savefig(a.output/'native-auto-overview.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4.8),layout='constrained')
    labels=[r['trial'].replace('ref533-','') for r in rows]
    colors=['#b6bbc4' if r['reference_counts']==520 else '#bf8d53' if r['bw']==6 else '#4a9976' for r in rows]
    bars=ax.barh(np.arange(len(rows)),[r['longest_BAL_observed_s'] for r in rows],color=colors)
    ax.set_yticks(np.arange(len(rows)),labels,fontsize=9);ax.invert_yaxis();ax.set_xlim(0,26)
    for bar,r in zip(bars,rows):ax.text(bar.get_width()+.15,bar.get_y()+bar.get_height()/2,f'{r["longest_BAL_observed_s"]:.3f}s',va='center',fontsize=9)
    ax.set_xlabel('Longest uninterrupted native BAL with observed endpoints (seconds)');ax.grid(axis='x',alpha=.2)
    ax.set_title('Native controller BAL duration, separate from physical acceptance')
    fig.savefig(a.output/'native-bal-durations.png',dpi=170);plt.close(fig)
    print(json.dumps(dict(output=str(a.output),trials=len(rows)),indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
