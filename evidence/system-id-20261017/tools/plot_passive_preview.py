#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "matplotlib>=3.9,<4"]
# ///
"""Plot strided unscored measurements for selecting manual release intervals."""
import argparse,gzip,json,math
from pathlib import Path
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise ValueError('output exists')
d=json.loads(gzip.decompress(a.input.read_bytes()));s=np.asarray(d['states']);t=(s[:,0]-s[0,0])/1e6;q=np.unwrap(s[:,2]);q=np.degrees(q-math.pi)
fig,axes=plt.subplots(3,1,figsize=(15,9),layout='constrained')
axes[0].plot(t,q);axes[0].set_ylabel('Raw encoder from pi (deg)');axes[0].set_xticks(np.arange(0,181,5));axes[0].grid()
v=[r for r in d['vision'] if r[1] is not None and r[2] is not None and r[3]>=.5 and r[4]];host0=float(np.quantile(s[:,1]/1e9-t,.01));vtime=np.array([r[0]-host0 for r in v]);angle=np.degrees([r[1] for r in v]);axes[1].plot(vtime,angle,'.',ms=1);axes[1].set_ylabel('Image angle (deg)');axes[1].set_xticks(np.arange(0,181,5));axes[1].grid()
axes[2].plot(vtime,[r[2][0] for r in v],'.',ms=1);axes[2].set_ylabel('Pivot x (px)');axes[2].set_xticks(np.arange(0,181,5));axes[2].grid();axes[2].set_xlabel('Board relative time / host receipt proxy (s)')
fig.suptitle('Unscored manual-release preview; strided data, timing proxy only')
fig.savefig(a.output,dpi=130)
for i in range(0,180,2):
 x=q[(t>=i)&(t<i+2)]
 if len(x) and np.ptp(x)>4:print(i,round(min(x),2),round(max(x),2))
