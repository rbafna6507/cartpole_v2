import glob,gzip,json,numpy as np
from scipy import signal
ROOT='/Users/rbafna/projects/cartpole_v2/evidence/phase3/retuning-20261016'
Q=2*np.pi/4096
BANDS=[(0,2),(2,4),(4,9),(9,30),(30,100)]
def gains(p):
 L=p['leff'];b1=2*p['pz']*p['pw'];b0=p['pw']**2;c1=-(p['pc1']+p['pc2']);c0=p['pc1']*p['pc2'];k3=-b0*c0*L/9.81;k4=-(b1*c0+b0*c1)*L/9.81;k1=L*k3-9.81-L*(b0+b1*c1+c0);k2=L*(k4-b1-c1)
 return -np.array([k1,k2,k3,k4])
def spectrum(y):return signal.welch(y,250,nperseg=2048)
def bandpower(f,p,a,b):
 m=(f>=a)&(f<b);return float(np.trapezoid(p[m],f[m]))
def stats(y):
 f,p=spectrum(y)
 return {'mean':float(np.mean(y)),'rms':float(np.sqrt(np.mean(y*y))),'std':float(np.std(y)),'abs95':float(np.percentile(abs(y),95)),'absmax':float(max(abs(y))),'peak_hz':float(f[1:][np.argmax(p[1:])]),'bands_rms':{f'{a}-{b}':float(np.sqrt(bandpower(f,p,a,b))) for a,b in BANDS}}
def phase(x,y,fr):
 f,P=signal.csd(x,y,250,nperseg=2048);_,X=spectrum(x);_,c=signal.coherence(x,y,250,nperseg=2048);i=np.argmin(abs(f-fr));return {'hz':float(f[i]),'gain':float(abs(P[i]/X[i])),'phase_deg':float(np.angle(P[i],deg=True)),'coherence':float(c[i])}
def load(p):
 r=json.load(gzip.open(p)); rows=sorted({s['unwrapped_tick']:s for s in r['states']}.values(),key=lambda s:s['unwrapped_tick']); d={k:np.array([s[k] for s in rows]) for k in ['unwrapped_tick','mode','theta','angle_hat','omega','x','velocity','acceleration','demand','brake_direction']};d['t']=(d['unwrapped_tick']-r['motion_start']['unwrapped_tick'])/1000;return r,d
runs={}
for token in ['ag5confirm60','ag7confirm60','-pw3-t1-']:
 p=next(p for p in glob.glob(ROOT+'/captures/*/report.json.gz') if token in p);r,d=load(p); m=(d['mode']==3)&(d['t']>=5)&(d['t']<min(59.5,r['requested_s']-.5));ss=np.flatnonzero(m)
 if token=='-pw3-t1-':ss=ss[d['t'][ss]>=4]
 native={k:d[k][ss] for k in d};grid=np.arange(native['t'][0],native['t'][-1]+.00001,.004);s={k:np.interp(grid,native['t'],v) for k,v in native.items()};s['t']=grid;terms=gains(r['parameters'])[:,None]*np.array([s[k] for k in ['angle_hat','omega','x','velocity']]);reconstructed=sum(terms);terms=dict(zip(['angle','rate','position','velocity'],terms));jerk=np.diff(native['acceleration'])/np.diff(native['t']); reqjerk=np.diff(native['demand'])/np.diff(native['t']);f,pdem=spectrum(s['demand']);fr=f[np.argmax(pdem*(f>=4)*(f<9))];freqhi=f[np.argmax(pdem*(f>=9)*(f<30))]
 out={'parameters':r['parameters'],'samples':len(ss),'window':[float(grid[0]),float(grid[-1])],'native_dt_ms':dict(zip(*[[str(x) for x in np.unique(np.round(np.diff(native['t'])*1000)).tolist()],np.unique(np.round(np.diff(native['t'])*1000),return_counts=True)[1].tolist()])),'statistics':{k:stats(s[k]) for k in ['theta','angle_hat','omega','x','velocity','acceleration','demand']},'terms':{k:stats(v) for k,v in terms.items()},'sampled_jerk':stats(jerk),'sampled_requested_jerk':stats(reqjerk),'jerk_fraction_over145':float(np.mean(abs(jerk)>145)),'reqjerk_fraction_over150':float(np.mean(abs(reqjerk)>150)),'tracking_error':stats(s['demand']-s['acceleration']),'reconstruction_error':stats(s['demand']-reconstructed),'applied_phase':{str(freq):phase(s['demand'],s['acceleration'],freq) for freq in [fr,freqhi,1,2,4,6,8,10,15,20]},'observer_phase':phase(s['theta'],s['omega'],fr),'gain_coefficients':gains(r['parameters']).tolist(),'term_share':{},'brake_samples':int(sum(native['brake_direction']!=0))}
 for a,b in BANDS:
  _,precon=spectrum(reconstructed);den=bandpower(f,precon,a,b);out['term_share'][f'{a}-{b}']={k:bandpower(f,signal.csd(v,reconstructed,250,nperseg=2048)[1].real,a,b)/den for k,v in terms.items()}
 runs[token]={'r':r,'s':s,'terms':terms,'out':out}
with open(str(__import__('pathlib').Path(__file__).with_name('bw10-jitter-results.json')),'w') as f:json.dump({n:z['out'] for n,z in runs.items()},f,indent=2)
for n,z in runs.items():
 o=z['out'];print('\n',n,'window',o['window'],'samples',o['samples'],'dt',o['native_dt_ms']);print('gains',o['gain_coefficients'])
 for k in ['theta','omega','velocity','acceleration','demand']:
  v=o['statistics'][k];print(k,'rms',round(v['rms'],5),'std',round(v['std'],5),'max',round(v['absmax'],4),'peak',round(v['peak_hz'],3),'bands', {k:round(x,5) for k,x in v['bands_rms'].items()})
 for k,v in o['terms'].items():print('term',k,'bands',{k:round(x,5) for k,x in v['bands_rms'].items()})
 print('covshares',o['term_share']);print('jerk', {k:v for k,v in o['sampled_jerk'].items() if k!='bands_rms'},'duty',o['jerk_fraction_over145'],'req_duty',o['reqjerk_fraction_over150']);print('error rms',o['tracking_error']['rms'],'recon rms',o['reconstruction_error']['rms']);print('phase',o['applied_phase']);print('observer',o['observer_phase']);print('brakes',o['brake_samples'])
