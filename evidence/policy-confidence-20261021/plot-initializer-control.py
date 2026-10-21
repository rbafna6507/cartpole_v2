#!/usr/bin/env python3
"""Plot every paired initializer/selected pose without choosing a new candidate."""
import json,os
from pathlib import Path
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/tmp/cartpole-confidence-mpl')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent

def main():
    data=json.loads((HERE/'initializer-control-comparison.json').read_text());fig,axes=plt.subplots(2,2,figsize=(11,8),layout='constrained')
    specs=[('hanging','first_one_second_capture_s','Hanging: first one-second capture','Seconds (65 = no capture)',1.),('hanging','longest_balance_dwell_s','Hanging: longest continuous balance','Seconds',1.),('upright','final_window_x_rms_m','Upright: final five-second cart RMS','Millimeters',1000.),('upright','max_abs_x_m','Upright: worst cart displacement','Millimeters',1000.)]
    for ax,(start,metric,title,ylabel,scale) in zip(axes.flat,specs):
        rr=[r for r in data['paired'] if r['start']==start];x=np.arange(len(rr))
        for i,r in enumerate(rr):
            a=r['initial_'+metric];b=r['selected_'+metric]
            if a is not None and b is not None:ax.plot([i-.12,i+.12],[a*scale,b*scale],color='#94a3b8',lw=1,zorder=1)
        for label,shift,color in [('initial',-.12,'#64748b'),('selected',.12,'#0f766e')]:
            y=[r[label+'_'+metric]*scale if r[label+'_'+metric] is not None else 65 if metric=='first_one_second_capture_s' else np.nan for r in rr]
            ax.scatter(x+shift,y,label=label,color=color,s=45,zorder=3)
            if start=='hanging':
                failed=[i for i,r in enumerate(rr) if not r[label+'_hold_success']]
                ax.scatter([i+shift for i in failed],[y[i] for i in failed],marker='x',s=85,color='#b45309',zorder=4)
        ax.set(title=title,xlabel='Pose seed − 96000',ylabel=ylabel,xticks=x);ax.grid(axis='y',alpha=.2)
    axes[0,0].axhline(5,color='#b45309',linestyle='--',lw=1);axes[0,0].set_ylim(-1,69)
    axes[0,1].axhline(30,color='#b45309',linestyle='--',lw=1);axes[0,1].set_ylim(0,62)
    axes[1,1].axhline(120,color='#b45309',linestyle='--',lw=1)
    axes[0,0].legend();selected=data['selected']
    fig.suptitle(f"Paired 60-second nominal control: initial actor → {selected['group']} seed {selected['optimizer_seed']}",fontsize=14)
    fig.supxlabel('Eight common poses. Orange × marks no final hold. Control declared after selection, before outcome inspection. Candidate unchanged.',fontsize=9)
    path=HERE/'initializer-control-comparison.png';assert not path.exists();fig.savefig(path,dpi=180);plt.close(fig);print(path)
if __name__=='__main__':main()
