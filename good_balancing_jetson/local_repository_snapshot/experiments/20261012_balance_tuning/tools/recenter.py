"""Slowly return to existing pulse-based home; never redefine home."""
import sys,os,time,json,argparse
sys.path.insert(0,os.getcwd())
from cartpole import Link
p=argparse.ArgumentParser();p.add_argument('--name',required=True);a=p.parse_args()
link=Link('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',logdir='../experiments/20261012_balance_tuning/'+a.name,reconnect=False,verbose=False)
try:
 link.send('stop');link.send('rate 100');link.send('params');time.sleep(.6)
 def state():
  if link.rx_error or time.monotonic()-(link.last_telemetry_at or 0)>.25:raise RuntimeError('Telemetry stale')
  with link.lock:return {k:v[-1] if v else None for k,v in link.buf.items()}
 start=time.monotonic()
 while True:
  s=state()
  if abs(s['x'])>link.params['rail']-.005 or abs(s['v'])>.06:raise RuntimeError('Recenter envelope exceeded')
  if s['mode'] not in (0,1):raise RuntimeError('Unexpected mode')
  if abs(s['x'])<.001 and abs(s['v'])<.005:break
  if time.monotonic()-start>20:raise RuntimeError('Recenter timeout')
  v=max(-.04,min(.04,-1.5*s['x']))
  if not link.send('v %.5f'%v):raise RuntimeError('Recenter command blocked')
  time.sleep(.05)
 link.send('v 0');time.sleep(.5);link.send('stop')
 start=time.monotonic();quiet=0
 while time.monotonic()-start<30:
  time.sleep(.1);s=state()
  if abs(s['theta'])>2.8 and abs(s['theta_dot'])<.15:quiet+=.1
  else:quiet=0
  if quiet>=1:break
 if quiet<1:raise RuntimeError('Pendulum did not settle hanging')
 print('RECENTERED_AND_SETTLED',json.dumps(s),flush=True)
finally:link.send('stop');link.send('rate 25');link.close()
