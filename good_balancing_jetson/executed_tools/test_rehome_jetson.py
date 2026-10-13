import importlib.util,sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
spec=importlib.util.spec_from_file_location('console_rehome','/tmp/cartpole_rehome.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
folder=Path('../experiments/20261012_balance_tuning/rehome_01');folder.mkdir(exist_ok=False)
link=m.Link('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',logdir=str(folder),reconnect=False,verbose=False)
def state():
 if link.telemetry_warning() or time.monotonic()-(link.last_telemetry_at or 0)>.25:raise RuntimeError('Unhealthy telemetry')
 with link.lock:return {k:v[-1] if v else None for k,v in link.buf.items()}
try:
 link.send('stop');link.send('rate 50');link.send('params');time.sleep(.6)
 before=state();assert before['mode']==0 and abs(before['x'])<.002 and before['v']==0 and abs(before['theta'])>2.8
 start=time.monotonic()
 while state()['x']<.006:
  s=state();assert time.monotonic()-start<2 and abs(s['x'])<.012 and abs(s['v'])<.02 and s['mode'] in (0,1)
  assert link.send('v 0.01000');time.sleep(.04)
 link.send('v 0');time.sleep(.5);link.send('stop')
 start=time.monotonic()
 while abs(state()['theta_dot'])>.15:
  assert time.monotonic()-start<20;time.sleep(.1)
 offset=state(); print('TEST_OFFSET',json.dumps(offset),flush=True)
 success=m.rehome(link);time.sleep(.4);after=state();assert success and abs(after['x'])<.001 and after['v']==0 and after['mode']==0
 result={'success':success,'before':before,'offset':offset,'after':after,'parameters':dict(link.params),'note':'Small positive offset and real console return to existing home, no home/upright commands.'}
 (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('REHOME_VERIFIED',json.dumps(result),flush=True)
finally:link.send('stop');link.send('rate 25');link.close()
