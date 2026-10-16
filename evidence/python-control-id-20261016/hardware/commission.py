import argparse,json,time,math,statistics,traceback,gc
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.policy import run_policy,run_host_controller,ZeroAccelerationPolicy
from cartpole_sdk.contracts import Channel
from cartpole_sdk.control.parameters import ControllerParameters,gains
from cartpole_sdk.control.forecast import can_capture_fast
from cartpole_sdk.sensing.telemetry import EncoderPublisher

parser=argparse.ArgumentParser();parser.add_argument('case',choices=('preflight','rehome','zero','auto','native'))
parser.add_argument('--seconds',type=float,default=1.);parser.add_argument('--rate',type=int,choices=(100,250),default=250)
args=parser.parse_args();assert 0<args.seconds<=25
root=Path('/home/rbafna/cartpole-v2-runs/python-id-20261016');directory=root/(args.case+'-'+str(time.time_ns()));directory.mkdir(parents=True)
gc_events=[];gc_start={}
def gc_trace(phase,info):
 now=time.monotonic_ns();generation=info['generation']
 if phase=='start':gc_start[generation]=now
 else:gc_events.append(dict(start_ns=gc_start.get(generation,now),end_ns=now,generation=generation,collected=info['collected']))
gc.callbacks.append(gc_trace)
report={'case':args.case,'rate_hz':args.rate,'requested_s':args.seconds,'path':str(directory)}
port='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
try:
 with Rig(port,rate_hz=args.rate,log_dir=directory,record_capacity=2048,vision_publisher=EncoderPublisher()) as rig:
  try:
   report['log']=str(rig.log_path)
   report['before_info']=asdict(rig.get_info());report['parameters']=rig.get_parameters()
   report['before_state']=asdict(rig._stopped_healthy())
   if report['before_info']['encoder_upright_raw']!=330:raise RuntimeError('upright reference changed; investigate before motion')
   state=rig.state
   if not(state.homed and state.healthy and state.switch_profile and not state.enabled):raise RuntimeError('requires healthy switch-protected home')
   if args.case=='rehome':
    rig.rehome();deadline=time.monotonic()+16
    while rig.state.enabled:
     if time.monotonic()>deadline:raise TimeoutError('initial rehome deadline')
     rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
    report['return_completed']=bool(abs(rig.state.x)<.001 and not rig.state.enabled)
   if args.case not in ('preflight','rehome') and abs(state.x)>.003:raise RuntimeError('start requires cart at saved home')
   p=ControllerParameters(**report['parameters']);k=gains(p)
   start=time.perf_counter_ns()
   for i in range(1000):can_capture_fast(p,k,.05,-.1,0.,0.,0.)
   report['forecast_mean_us']=(time.perf_counter_ns()-start)/1e6
   rig.save_parameters(directory/'parameters.json')
   print(json.dumps({'preflight':report['before_info'],'bw':p.bw,'forecast_mean_us':report['forecast_mean_us']}),flush=True)
   samples=[];end=time.monotonic()+2
   while time.monotonic()<end:
    state=rig.wait_state(after_tick=state.unwrapped_tick,timeout=.1);samples.append(asdict(state))
   report['stopped_samples']=samples
   if args.case not in ('preflight','rehome'):
    if abs(samples[-1]['omega'])>.3 or abs(abs(samples[-1]['theta'])-math.pi)>.35:raise RuntimeError('pole not quietly hanging')
    if args.case=='zero':
     channels=(Channel('pole','angle','magnetic','encoder-zero'),Channel('cart','position','step','cart-step-home'))
     run_policy(rig,ZeroAccelerationPolicy,channels=channels,duration_s=args.seconds,max_acceleration=.25)
    elif args.case=='auto':run_host_controller(rig,mode='auto',duration_s=args.seconds)
    else:
     rig.start('auto',args.seconds)
     deadline=time.monotonic()+args.seconds+16
     while rig.state.enabled:
      if time.monotonic()>deadline:raise TimeoutError('native trial did not finish')
      rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
    report['after_trial']=asdict(rig.state)
    if abs(rig.state.x)>.0001:
     rig.rehome();deadline=time.monotonic()+16
     while rig.state.enabled:
      if time.monotonic()>deadline:raise TimeoutError('rehome deadline')
      rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
    report['return_completed']=bool(not rig.state.enabled and abs(rig.state.x)<.001)
   report['final_info']=asdict(rig.get_info());report['final_state']=asdict(rig.state)
  except BaseException as exc:
   report['failure']=repr(exc);report['traceback']=traceback.format_exc();raise
  finally:
   try:rig.stop();report['stop_state']=asdict(rig.state)
   finally:
    report['gc_events']=gc_events
    (directory/'report.json').write_text(json.dumps(report,indent=2))
finally:
 print(json.dumps({'report':str(directory/'report.json'),'failure':report.get('failure'),'return_completed':report.get('return_completed')}),flush=True)
