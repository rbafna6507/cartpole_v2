"""Operator-assisted passive recording. Driver stays disabled; no ARM/MODE/HOME."""
import argparse,hashlib,json,os,subprocess,time,traceback
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher

def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--seconds',type=float,default=180);a=p.parse_args()
 if not 1<=a.seconds<=180:raise ValueError('passive recording bounded to180seconds')
 a.directory.mkdir(parents=True,exist_ok=False);report={'case':'manual-passive','requested_s':a.seconds,'started_ns':time.monotonic_ns(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()};camera=None
 try:
  with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=a.directory,record_capacity=4096,vision_publisher=EncoderPublisher()) as rig:
   try:
    rig.stop();s=rig._stopped_healthy();info=rig.get_info();report['before_state']=asdict(s);report['info']=asdict(info);report['parameters']=rig.get_parameters();report['log']=str(rig.log_path)
    if info.encoder_upright_raw!=330 or info.firmware!='executor-v6-measuredrail' or not(s.homed and s.switch_profile) or abs(s.x)>.003:raise RuntimeError('unexpected reference/firmware/home state')
    cmd=['taskset','-c','4','/home/rbafna/cartpole_v2/.venv/bin/python',str(Path(__file__).with_name('record_vision_raw.py')),'--directory',str(a.directory),'--seconds',str(a.seconds+5)]
    output=(a.directory/'vision-process.txt').open('x');camera=subprocess.Popen(cmd,stdout=output,stderr=subprocess.STDOUT);end=time.monotonic()+a.seconds
    report['recording_started_ns']=time.monotonic_ns();print(json.dumps({'recording':str(a.directory),'disabled':not s.enabled,'reference':info.encoder_upright_raw,'seconds':a.seconds,'camera_pid':camera.pid}),flush=True)
    while time.monotonic()<end and not(a.directory/'stop-recording').exists():
     if camera.poll() is not None:raise RuntimeError('vision recorder ended before passive session')
     s=rig.wait_state(after_tick=s.unwrapped_tick,timeout=.15)
     if s.enabled or s.fault or not s.healthy or not s.homed:raise RuntimeError('passive driver/health state changed')
    report['finished_state']=asdict(rig.state)
   except BaseException as exc:report['failure']=repr(exc);report['traceback']=traceback.format_exc();raise
   finally:
    rig.stop();report['stop_state']=asdict(rig.state);report['records_dropped']=rig.records_dropped
 finally:
  (a.directory/'stop-recording').touch()
  if camera is not None:
   try:camera.wait(timeout=3)
   except subprocess.TimeoutExpired:camera.terminate();camera.wait(timeout=3)
   report['camera_returncode']=camera.returncode;output.close()
  report['finished_ns']=time.monotonic_ns()
  if report.get('log') and Path(report['log']).exists():report['raw_log_sha256']=hashlib.sha256(Path(report['log']).read_bytes()).hexdigest()
  (a.directory/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(a.directory/'report.json'),'failure':report.get('failure'),'camera_returncode':report.get('camera_returncode')}),flush=True)
if __name__=='__main__':main()
