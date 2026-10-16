"""Run the actual read-only shadow CLI while one stopped Rig owns serial."""
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from dataclasses import asdict
from pathlib import Path
import json,time,subprocess,sys,urllib.request,gzip,collections
root=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')/('sdk-shadow-batch-'+str(time.time_ns()))
root.mkdir(parents=True)
config=json.loads(Path('/tmp/proposed-live-shadow-config.json').read_text())
config['session_id']='stopped-batch-shadow-'+str(time.time_ns())
(root/'configuration.json').write_text(json.dumps(config,indent=2))
report=dict(path=str(root),success=False);child=None
def fetch(path):
    with urllib.request.urlopen('http://127.0.0.1:3090'+path,timeout=1) as f:return json.load(f)
try:
    with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,vision_publisher=EncoderPublisher()) as rig:
        try:
            rig.stop();info=rig.get_info();report['initial_info']=asdict(info)
            assert info.firmware=='executor-v4-rehome' and info.encoder_upright_raw==370
            # Wait for the current owner/reference rather than old cached viewer data.
            ready_deadline=time.monotonic()+2
            while True:
                packet=fetch('/api/encoder').get('packet')
                if packet and packet['sdk_state']['sid']==rig.state.sid and packet['sdk_info']:break
                assert time.monotonic()<ready_deadline
                time.sleep(.01)
            with (root/'monitor.log').open('w') as log:
                child=subprocess.Popen([sys.executable,'examples/sensing_shadow.py','--config',str(root/'configuration.json'),
                    '--output',str(root/'capture.jsonl'),'--duration','25','--poll-hz','100'],stdout=log,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+35
                while child.poll() is None:
                    state=rig.state
                    assert not state.enabled and state.mode==0 and state.healthy and state.homed and state.switch_profile and not state.fault
                    assert abs(state.x)<.001 and rig.error is None and time.monotonic()<deadline
                    time.sleep(.02)
            report['monitor_returncode']=child.returncode
            assert child.returncode==0,(root/'monitor.log').read_text()[-2000:]
            viewer=fetch('/api/sdk-state?compact=1');viewer.pop('samples',None);report['viewer']=viewer
        finally:
            if child and child.poll() is None:child.terminate();child.wait(timeout=3)
            rig.stop();report['final']=asdict(rig.state);report['final_info']=asdict(rig.get_info())
    time.sleep(.7)
    viewer=fetch('/api/sdk-state?compact=1');report['after_close_status']=viewer['status']
    report['after_close_encoder']=fetch('/api/state')['comparison']['status']
    assert viewer['status']=='stale'
    counts=collections.Counter();last=None;rows=0
    with (root/'capture.jsonl').open() as f:
        for line in f:
            row=json.loads(line);rows+=1
            if row.get('type')=='shadow':
                last=row['packet'];counts[last['diagnostics']['status']]+=1
    report['counts']=dict(counts);report['rows']=rows;report['last_diagnostics']=last['diagnostics'] if last else None
    assert last and last['diagnostics']['accepted_vision']>20
    assert last['commissioned'] is False and last['control_eligible'] is False
    assert any(s['source']=='fused' and s['validity']=='valid' for s in last['observation']['samples'])
    report['success']=True
except BaseException as exc:report['success']=False;report['error']=repr(exc)
finally:
    (root/'summary.json').write_text(json.dumps(report,indent=2))
    capture=root/'capture.jsonl'
    if capture.exists():(root/'capture.jsonl.gz').write_bytes(gzip.compress(capture.read_bytes()))
    print(json.dumps({k:v for k,v in report.items() if k!='viewer'},indent=2),flush=True)
if not report['success']:raise SystemExit(1)
