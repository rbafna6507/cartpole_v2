#!/usr/bin/env python3
"""Plot frozen balance-candidate sensitivity to upstream encoder zero error."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
base=Path(__file__).resolve().parent/'balance47-encoder-sensitivity'
report=json.loads((base/'report.json').read_text())
fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
colors={0:'#147d73',-.25:'#b45635',.25:'#405faf'}
for bias,color in colors.items():
    episode=next(e for e in report['episodes'] if e['encoder_bias_degrees']==bias and e['seed']==94000)
    rows=[json.loads(l) for l in (base/episode['trace_path']).open()]
    truth=[r['ground_truth_after'] for r in rows]
    t=(np.array([r['time_ns'] for r in truth])-episode['reset_warmup_ns'])/1e9
    axes[0].plot(t,[1000*r['x'] for r in truth],color=color,label=f'{bias:+g}° encoder offset')
axes[0].axhline(120,color='0.5',ls='--',lw=1,label='Balance centering bound')
axes[0].axhline(-120,color='0.5',ls='--',lw=1)
axes[0].set(title='Same starting state, unchanged policy',xlabel='Time (s)',ylabel='True simulated cart position (mm)')
axes[0].legend(fontsize=8)
summary=sorted(report['summary'],key=lambda r:r['encoder_bias_degrees'])
axes[1].bar([str(r['encoder_bias_degrees']) for r in summary],[1000*r['mean_final_window_x_rms_m'] for r in summary],color=['#147d73' if r['encoder_bias_degrees']==0 else '#b45635' for r in summary])
axes[1].set(title='Both tested starts: final 5-second RMS',xlabel='Constant encoder offset (degrees)',ylabel='True simulated cart position RMS (mm)')
for a in axes:a.grid(alpha=.18,axis='y')
fig.suptitle('Balance candidate: a three-count angle offset is a material transfer gap',fontsize=12)
fig.savefig(base/'sensitivity.png',dpi=170)
