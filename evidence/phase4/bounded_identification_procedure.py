"""Trusted bounded characterization. Explicit no-switch commissioning; not a submitted policy."""
import math,json,time,pathlib,datetime,traceback
from dataclasses import asdict
from cartpole_sdk.rig import Rig
PORT='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
DURATION=20.; RAMP=2.
def trajectory(t,amplitude,frequencies):
 if t<0 or t>DURATION:return 0.,0.,0.
 if t<RAMP:
  q=math.pi*t/RAMP;e=.5*(1-math.cos(q));ed=.5*math.pi/RAMP*math.sin(q);edd=.5*(math.pi/RAMP)**2*math.cos(q)
 elif t>DURATION-RAMP:
  q=math.pi*(DURATION-t)/RAMP;e=.5*(1-math.cos(q));ed=-.5*math.pi/RAMP*math.sin(q);edd=.5*(math.pi/RAMP)**2*math.cos(q)
 else:e,ed,edd=1.,0.,0.
 g=sum(amplitude*math.sin(2*math.pi*f*t) for f in frequencies)
 gd=sum(amplitude*2*math.pi*f*math.cos(2*math.pi*f*t) for f in frequencies)
 gdd=sum(-amplitude*(2*math.pi*f)**2*math.sin(2*math.pi*f*t) for f in frequencies)
 return e*g,ed*g+e*gd,edd*g+2*ed*gd+e*gdd
TRIALS=[('train1',.0005,(.8,1.3,2.1)),('validation1',.0004,(.7,1.6,2.3))]
def check_waveforms():
 result={}
 for name,a,fs in TRIALS:
  rows=[trajectory(i/1000,a,fs) for i in range(20001)]
  peaks=[max(abs(r[j]) for r in rows) for j in range(3)]
  assert peaks[0]<.0016 and peaks[1]<.015 and peaks[2]<.16,peaks
  assert trajectory(0,a,fs)==(0.,0.,0.)
  assert all(abs(v)<1e-12 for v in trajectory(DURATION,a,fs))
  for i in (500,1000,3000,6000,19000,19500):
   t=i/1000;h=1e-5;m=trajectory(t-h,a,fs);p=trajectory(t+h,a,fs);mid=trajectory(t,a,fs)
   assert abs((p[0]-m[0])/(2*h)-mid[1])<1e-7
   assert abs((p[1]-m[1])/(2*h)-mid[2])<1e-6
  result[name]={'max_target_x_m':peaks[0],'max_target_v_m_s':peaks[1],'max_feedforward_a_m_s2':peaks[2]}
 return result
if __name__=='__main__':
 import sys
 bounds=check_waveforms()
 if '--verify-only' in sys.argv:print(json.dumps(bounds,indent=2));raise SystemExit(0)
 root=pathlib.Path.home()/'cartpole-v2-runs'/('identification-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));root.mkdir(parents=True)
 report={'path':str(root),'planned_bounds':bounds,'hard_host_guards':{'abs_x_m':.015,'abs_v_m_s':.03,'abs_a_m_s2':.25,'abs_omega_rad_s':10},'position_basis':'step-derived only; no independent metric cart signal','trials':[]}
 try:
  with Rig(PORT,rate_hz=250,log_dir=root,record_capacity=4096) as rig:
   try:
    rig.stop();info=rig.get_info();assert info.encoder_upright_raw==3485 and info.reference_saved
    assert rig.state.healthy and abs(rig.state.theta)>2.8 and abs(rig.state.omega)<.3
    rig.configure_switches(False);rig.center()
    for name,amplitude,frequencies in TRIALS:
     print('START '+name,flush=True)
     rows=[];report['trials'].append({'name':name,'amplitude_m':amplitude,'frequencies_hz':frequencies,'rows':rows})
     rig.arm(21);start=rig.state.unwrapped_tick
     while True:
      state=rig.state;t=(state.unwrapped_tick-start)/1000
      assert state.healthy and state.enabled and abs(state.x)<.015 and abs(state.velocity)<.03 and abs(state.omega)<10
      if t>=DURATION:break
      x,v,a=trajectory(t,amplitude,frequencies);demand=max(-.25,min(.25,a+40*(x-state.x)+8*(v-state.velocity)))
      seq=rig.set_acceleration(demand,30)
      rows.append({'t_s':state.unwrapped_us/1e6,'theta_rad':state.theta,'omega_rad_s':state.omega,'cart_acceleration_m_s2':state.acceleration,'x_m':state.x,'v_m_s':state.velocity,'demand':demand,'seq':seq,'tick':state.tick,'host_received_ns':state.received_ns,'target_x_m':x,'valid':True,'run_id':name,'calibration_id':'encoder-upright3485','frame_id':'encoder-zero','clock_id':rig.session.clock_id})
      rig.wait_state(after_tick=state.tick,timeout=.1)
     # Stop from a near-rest boundary; controller has tracked the full smooth fade.
     rig.set_acceleration(0.,30);rig.stop()
     assert abs(rig.state.x)<.006 and abs(rig.state.velocity)<.001
     report['trials'][-1]['final']=asdict(rig.state)
     print('DONE '+name+' samples='+str(len(rows))+' peakx='+str(max(abs(r['x_m']) for r in rows)),flush=True)
     # Record passive ringing with no actuator demands between independent trials.
     time.sleep(3.)
    report['ok']=True
   finally:
    rig.stop()
    if rig.error is not None:
     try:rig.clear_fault()
     except Exception as exc:report['restore_clear_error']=str(exc)
    try:rig.configure_switches(True)
    except Exception as exc:report['restore_switch_error']=str(exc)
    if rig.error is None:rig.set_rate(0)
    rig.stop();report['final']=asdict(rig.state);report['info']=asdict(rig.get_info())
 except BaseException as exc:report['ok']=False;report['error']=repr(exc);report['traceback']=traceback.format_exc()
 finally:
  (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
  summary={k:v for k,v in report.items() if k!='trials'};summary['trials']=[{k:v for k,v in trial.items() if k!='rows'}|{'samples':len(trial['rows'])} for trial in report['trials']];print(json.dumps(summary,indent=2),flush=True)
 if not report.get('ok'):raise SystemExit(1)
