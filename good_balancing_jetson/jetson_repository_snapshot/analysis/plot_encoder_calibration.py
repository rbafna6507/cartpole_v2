#!/usr/bin/env python3
"""Plot four raw encoder reference points without fitting a correction."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def analyze(report):
    points=sorted(report['calibration']['points'],key=lambda p:p['reference_deg'])
    if [p['reference_deg'] for p in points]!=[0,90,180,270]:
        raise ValueError('Expected the four recorded reference angles 0, 90, 180, 270')
    degrees=np.array([p['reference_deg'] for p in points],dtype=float)
    raw=np.array([p['raw'] for p in points],dtype=float)
    cpr=report['calibration']['raw_counts_per_turn']
    unwrapped=np.unwrap(raw*2*np.pi/cpr)*cpr/(2*np.pi)
    direction=1 if unwrapped[-1]>unwrapped[0] else -1
    ideal=raw[0]+direction*cpr*degrees/360
    measured=direction*(unwrapped-raw[0])*360/cpr
    errors=measured-degrees
    quadrants=direction*np.diff(np.append(unwrapped,unwrapped[0]+direction*cpr))
    return dict(reference_deg=degrees.tolist(),raw=raw.tolist(),unwrapped_counts=unwrapped.tolist(),
                ideal_counts_from_down=ideal.tolist(),angle_error_deg=errors.tolist(),
                quadrant_counts=quadrants.tolist(),direction=direction,
                upright_raw=raw[2],ideal_upright_raw=(raw[0]+cpr/2)%cpr,
                source_complete=report['complete'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--output',type=Path,help='output filename prefix without extension')
    args=parser.parse_args()
    report=json.loads(args.capture.read_text());data=analyze(report)
    output=args.output or args.capture.with_name(args.capture.stem+'_linearity')
    output.parent.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,(ax,err)=plt.subplots(2,1,figsize=(10,8),gridspec_kw={'height_ratios':[2.1,1]},layout='constrained')
    fig.suptitle('Pendulum encoder · four-position check',fontsize=19,fontweight='bold')
    x=data['reference_deg']
    ax.plot(x,data['ideal_counts_from_down'],'--',color='#7b8794',label='Ideal: 4096 counts/turn, anchored at 0°')
    ax.plot(x,data['unwrapped_counts'],'o-',color='#126e82',lw=2.2,label='Saved measurements (unwrapped)')
    ax.scatter([180],[data['unwrapped_counts'][2]],marker='*',s=220,color='#d27614',zorder=5,label=f"Measured upright: raw {data['upright_raw']:.1f}")
    for angle,raw,y in zip(x,data['raw'],data['unwrapped_counts']):
        ax.annotate(f'{int(angle)}°: raw {raw:.0f}',(angle,y),xytext=(-6 if angle==270 else 6,12),ha='right' if angle==270 else 'left',textcoords='offset points',fontsize=10)
    ax.set(ylabel='Encoder counts, unwrapped across zero',xlim=(-12,302))
    ax.set_xticks(x);ax.grid(alpha=.18);ax.legend(loc='lower left',fontsize=10)
    err.axhline(0,color='#7b8794',lw=1)
    bars=err.bar(x,data['angle_error_deg'],width=33,color=['#80929a','#126e82','#d27614','#126e82'])
    for bar,value in zip(bars,data['angle_error_deg']):
        err.annotate(f'{value:+.2f}°',(bar.get_x()+bar.get_width()/2,value),xytext=(0,5 if value>=0 else -15),textcoords='offset points',ha='center')
    err.set(xlabel='Manually positioned reference angle (degrees)',ylabel='Error from ideal (degrees)',xlim=(-12,302))
    lo=min(0,min(data['angle_error_deg']));hi=max(0,max(data['angle_error_deg']));pad=max(3,(hi-lo)*.18)
    err.set_ylim(lo-pad,hi+pad)
    err.set_xticks(x);err.grid(axis='y',alpha=.18)
    fig.get_layout_engine().set(rect=(0,.085,1,.90))
    counts=[p.get('sample_count',1) for p in report.get('poses',[])]
    invalid=sum(not s.get('valid',True) for p in report.get('poses',[]) for s in p.get('samples',[]))
    samples=[s for p in report.get('poses',[]) for s in p.get('samples',[])]
    weak=sum(bool(s.get('status',0)&0x10) for s in samples)
    strong=sum(bool(s.get('status',0)&0x08) for s in samples)
    note=f'Readings per pose: {counts}; stale/invalid: {invalid}; weak-magnet flags: {weak}; strong-magnet flags: {strong}.\nNo nonlinear correction fitted. Differences include manual placement and sensor error.'
    fig.text(.065,.035,note,fontsize=10,color='#58616b')
    for ext in ['png','svg']:
        fig.savefig(str(output)+'.'+ext,dpi=170,facecolor='white')
    Path(str(output)+'.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data,indent=2))

if __name__=='__main__':main()
