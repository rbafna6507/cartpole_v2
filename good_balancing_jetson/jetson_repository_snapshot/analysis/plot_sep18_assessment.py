from pathlib import Path
import json,numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
O=Path(__file__).resolve().parent/'sep18';data=json.loads((O/'decay_validation.json').read_text());result=json.loads((O/'final_validation.json').read_text());latest=json.loads((O/'recorded_trials.json').read_text())
plt.rcParams.update({'font.size':10,'font.family':'DejaVu Sans'})
fig,ax=plt.subplots(2,1,figsize=(11,7),layout='constrained',gridspec_kw={'height_ratios':[2,1]})
held=[r for r in data if r['window'][0]==294];p=np.array(held[0]['points']);ax[0].plot(p[:,0],np.degrees(p[:,1]),color='#183d51',label='Recorded after STOP',lw=1.7)
for r,color in zip(held,['#c97738','#158778']):
 p=np.array(r['points']);ax[0].plot(p[:,0],np.degrees(p[:,2]),color=color,label=f"{'Prior model' if r['model']=='prior' else 'Recent provisional fit'} · RMSE {r['rmse_deg']:.1f}°",lw=1.2)
ax[0].set(title='Separate stopped-motion window: recent fit is closer, but error remains',ylabel='Angle about hanging (°)',xlabel='Seconds after start of validation window');ax[0].legend(loc='upper right');ax[0].grid(alpha=.2)
ax[1].barh(['Recorded gains','Next-trial candidate'],[0,result['results'][0]['passes']],color=['#c97738','#158778']);ax[1].set(xlim=(0,18),xlabel='Cases ending with ≥5 continuous seconds of balance (out of 18)',title='60-second sensitivity checks · simulation only');ax[1].set_xticks([0,3,6,9,12,15,18]);ax[1].grid(axis='x',alpha=.2)
for i,n in enumerate([0,11]):ax[1].text(n+.2,i,str(n),va='center')
fig.savefig(O/'assessment.png',dpi=160,bbox_inches='tight')
