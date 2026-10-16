exec(open(__import__('pathlib').Path(__file__).with_name('bw10_jitter.py')).read().split('runs={}')[0])
from scipy import integrate
reports={}
for token in ['ag5confirm60','ag7confirm60']:
 path=next(p for p in glob.glob(ROOT+'/captures/*/report.json.gz') if token in p);r,d=load(path);m=(d['mode']==3)&(d['t']>=5)&(d['t']<59.5);t=d['t'][m];grid=np.arange(t[0],t[-1]+.00001,.004);s={k:np.interp(grid,t,v[m]) for k,v in d.items()};reports[token]=(r,s)
def transfer(f,bw):
 w=2*np.pi*bw;dt=.001;z=np.exp(2j*np.pi*np.asarray(f)*dt);den=(z-1+w*dt)**2
 # sampled after update: z*(zI-A)^-1*B
 return z*(2*w*dt*(z-1)+w*w*dt*dt)/den,z*w*w*dt*(z-1)/den
qvar=Q*Q/12
f=np.linspace(0,500,100001)
print('q',Q,'deg',np.degrees(Q),'noiseRMSrad',np.sqrt(qvar))
for bw in [30,10,9,8]:
 htheta,hrate=transfer(f,bw);k=gains(next(iter(reports.values()))[0]['parameters']);h=k[0]*htheta+k[1]*hrate;P=abs(h)**2*(2*qvar/1000)
 print('WHITE quant demand bw',bw,'all RMS',np.sqrt(np.trapezoid(P,f)),'bands',{f'{a}-{b}':round(np.sqrt(bandpower(f,P,a,b)),6) for a,b in BANDS},'angle->demand max',max(abs(h)),'deterministic_bound_RMS',float(max(abs(h))*Q/2))
 for freq in [1,2,6,7,10,15,20]:
  a,v=transfer(np.array([freq]),bw);a0,v0=transfer(np.array([freq]),10);h=k[0]*a+k[1]*v;h0=k[0]*a0+k[1]*v0
  print('TF',bw,freq,'rate_gain',round(abs(v[0]),3),'rate_phase',round(np.angle(v[0],deg=True),2),'demand_rel10',round(abs(h[0]/h0[0]),4),'phase_rel10',round(np.angle(h[0]/h0[0],deg=True),3))
for name,(r,s) in reports.items():
 n=len(s['theta']);f=np.fft.rfftfreq(n,.004);raw=np.fft.rfft(s['theta']);x=np.fft.rfft(s['x']);v=np.fft.rfft(s['velocity']);k=gains(r['parameters']);original=None
 print('\nREPLAY',name)
 for bw in [30,10,9,8]:
  ht,hr=transfer(f,bw);new=np.fft.irfft((k[0]*ht+k[1]*hr)*raw+k[2]*x+k[3]*v,n=n);st=stats(new);bs=st['bands_rms'];original=bs if bw==10 else original
  print('bw',bw,'RMSbands',bs,'delta10',{key:round(val/original[key]-1,4) for key,val in bs.items()} if original else None)
 theta=s['theta'];steps=np.diff(np.round(theta/Q));print('raw4mscountchange p50,p90,p95,p99,max',np.percentile(abs(steps),[50,90,95,99,100]).tolist(),'nonzero',float(np.mean(steps!=0)))
 print('rawbandsdeg',{k:np.degrees(v) for k,v in stats(theta)['bands_rms'].items()})
 print('rawbandsLSB',{k:v/Q for k,v in stats(theta)['bands_rms'].items()})
