"""Bounded, supervised auto trial. Run from Jetson console bundle directory."""
import sys,time,json,math,argparse,os
sys.path.insert(0,os.getcwd())
from cartpole import Link
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--settings',required=True);p.add_argument('--home',action='store_true');p.add_argument('--duration',type=float,default=35);args=p.parse_args()
folder='../experiments/20261012_balance_tuning/'+args.name
if os.path.exists(folder):raise SystemExit('Trial directory exists; refusing overwrite')
link=Link('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',logdir=folder,reconnect=False,verbose=False)
result={'name':args.name,'settings_requested':json.loads(args.settings),'result':'not started','time_start':time.time()}
try:
 link.send('stop');time.sleep(.3)
 if args.home:link.send('home');time.sleep(.1)
 for k,v in result['settings_requested'].items():
  if k not in ('rail','pw','pz','pc1','pc2','bw','leff','vmax','vmax_s','vmax_b','amax_s','amax_b','jmax','catch_a','catch_r','catch_da','catch_v','approach_v','approach_angle','ke','kpx','kdx','phase_soft'):raise RuntimeError('Unexpected setting '+k)
  link.send('set %s %s'%(k,v));time.sleep(.04)
 link.send('rate 100');link.send('params');time.sleep(.7)
 for k,v in result['settings_requested'].items():
  if abs(link.params.get(k,999)-v)>.0001:raise RuntimeError('Readback mismatch '+k)
 result['parameters']=dict(link.params)
 def state():
  if link.rx_error or time.monotonic()-(link.last_telemetry_at or 0)>.25:raise RuntimeError('Telemetry missing/stale')
  with link.lock:return {k:v[-1] if v else None for k,v in link.buf.items()}
 s=state()
 if s['mode']!=0 or abs(s['x'])>.015 or abs(s['v'])>.001:raise RuntimeError('Start requires stopped center '+str(s))
 if abs(s['theta'])<2.8 or abs(s['theta_dot'])>.3:raise RuntimeError('Start requires hanging still '+str(s))
 link.send('enc');time.sleep(.1)
 with link.lock:e=dict(link.encoder_samples[-1])
 if e['enabled'] or not e['valid'] or not e['status']&32:raise RuntimeError('Encoder/start-state check failed')
 result['start_state']=s
 if not link.send('auto'):raise RuntimeError('Auto blocked')
 print('AUTO_ACTIVE',args.name,flush=True)
 start=time.monotonic();last_print=0;last_encoder=0;hold=0;longest=0;prev_mode=0;catches=0;recoveries=0;peak_x=0;prev_t=None
 result['result']='duration limit'
 while time.monotonic()-start<args.duration:
  time.sleep(.01);s=state();now=time.monotonic()
  if now-last_encoder>.1:link.send('enc');last_encoder=now
  with link.lock:e=dict(link.encoder_samples[-1])
  if not e['valid']:raise RuntimeError('Invalid encoder snapshot')
  if s['mode']==4:result['result']='firmware fault';break
  if now-start>.3 and s['mode']==0:result['result']='unexpected idle';break
  if abs(s['x'])>link.params['rail']-.005:raise RuntimeError('Commanded position outside hard travel envelope')
  if abs(s['v'])>link.params['vmax']+.01:raise RuntimeError('Commanded speed beyond ceiling')
  dt=0 if prev_t is None else (s['t_ms']-prev_t)/1000
  if dt<0 or dt>.25:raise RuntimeError('Board clock discontinuity')
  if s['mode']==3 and prev_mode!=3:catches+=1
  if s['mode']==5 and prev_mode!=5:recoveries+=1
  if s['mode']==3 and abs(s['theta'])<math.radians(8) and abs(s['theta_dot'])<1 and abs(s['x'])<.15:hold+=dt
  else:hold=0
  longest=max(longest,hold);peak_x=max(peak_x,abs(s['x']));prev_t=s['t_ms'];prev_mode=s['mode']
  if now-last_print>2:print('STATE',json.dumps(s),'hold',round(hold,2),flush=True);last_print=now
  if hold>=15:result['result']='15s stable hold';break
 result['end_of_measurement_state']=s
 # For a normal time limit, stop near a velocity reversal to reduce unmeasured coast.
 if result['result'] in ('duration limit','15s stable hold'):
  deadline=time.monotonic()+3
  while abs(s['v'])>.04 and time.monotonic()<deadline:
   time.sleep(.005);s=state()
   if s['mode']==4 or abs(s['x'])>link.params['rail']-.005:break
  result['stop_speed_m_s']=s['v']
 result.update(final_state=s,catches=catches,rail_recoveries=recoveries,longest_stable_hold_s=longest,peak_commanded_x_m=peak_x,elapsed_s=time.monotonic()-start)
except BaseException as exc:
 result['result']='aborted';result['error']=repr(exc);print('ABORT',repr(exc),flush=True)
finally:
 link.send('stop');link.send('rate 25');link.close();result['time_end']=time.time()
 with open(os.path.join(folder,'result.json'),'w') as f:json.dump(result,f,indent=2)
 print('RESULT',json.dumps(result),flush=True)
