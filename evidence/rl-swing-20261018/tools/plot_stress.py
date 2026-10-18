#!/usr/bin/env python3
"""Plot complete hash-bound stress reports; failed checks remain visible."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    reports=[]
    for root in a.runs:
        report=json.loads((root/'report.json').read_text());recipe=root/'recipe.json'
        if not report['completed'] or sha256(recipe.read_bytes()).hexdigest()!=report['recipe_sha256']:raise ValueError('report recipe mismatch')
        for ep in report['episodes']:
            if sha256((root/ep['trace_path']).read_bytes()).hexdigest()!=ep['trace_sha256']:raise ValueError('trace mismatch')
        reports.append((root.name,report))
    scenarios=[r['scenario'] for r in reports[0][1]['summary'] if r['start']=='upright' and r['expected']=='task_success']
    columns=[];values=[];counts=[]
    for label,report in reports:
        for start in ('hanging','upright'):
            rows=[next(r for r in report['summary'] if r['start']==start and r['scenario']==s) for s in scenarios]
            columns.append(label.replace('stress-','').replace('-seed','\nseed')+'\n'+start);values.append([r['holds']/r['episodes'] for r in rows]);counts.append([f"{r['holds']}/{r['episodes']}" for r in rows])
    matrix=np.array(values).T;labels=np.array(counts).T
    fig,ax=plt.subplots(figsize=(max(8,len(columns)*1.55),6))
    ax.imshow(matrix,vmin=0,vmax=1,cmap='RdYlGn',aspect='auto')
    for (i,j),v in np.ndenumerate(matrix):ax.text(j,i,labels[i,j],ha='center',va='center',fontsize=11,color='white' if v in (0,1) else 'black')
    ax.set_xticks(range(len(columns)),columns,fontsize=9);ax.set_yticks(range(len(scenarios)),scenarios)
    ax.set_title('Frozen neural policies • final five-second holds in 25-second stress episodes',pad=15)
    fig.text(.5,.015,'Engineering sensitivity ranges; not measured uncertainty. Expected-stop fault tests are reported separately.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1));fig.savefig(a.output,dpi=170);plt.close(fig)

if __name__=='__main__':main()
