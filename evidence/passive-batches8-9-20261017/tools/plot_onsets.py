#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "matplotlib>=3.8,<4"]
# ///
"""Raw onset vicinity plots; no prediction, fit, residual or selection logic."""
import argparse,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);p.add_argument('--centers',type=float,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
z=np.load(a.cache);t,q=z['t'],np.rad2deg(z['q']);ct,cq=z['ct'],np.rad2deg(z['cq'])
f,axs=plt.subplots(math.ceil(len(a.centers)/3),3,figsize=(16,3.25*math.ceil(len(a.centers)/3)),layout='constrained',squeeze=False)
for n,(ax,c) in enumerate(zip(axs.flat,a.centers),1):
 ix=(t>=c-1)&(t<=c+.5);ci=(ct>=c-1)&(ct<=c+.5);ax.plot(t[ix],q[ix],label='encoder');ax.plot(ct[ci],cq[ci],label='camera');ax.grid();ax.set_xticks(np.round(np.arange(c-.8,c+.6,.1),2));ax.tick_params(axis='x',rotation=55);ax.set_title(f'Release {n} raw onset vicinity')
for ax in list(axs.flat)[len(a.centers):]:ax.set_visible(False)
axs.flat[0].legend();f.savefig(a.output,dpi=120)
