"""Stopped-only verification of SDK single-reader telemetry reaching the viewer."""
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from dataclasses import asdict
from pathlib import Path
import json,time,urllib.request
root=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')/('sdk-encoder-mirror-'+str(time.time_ns()))
root.mkdir(parents=True)
report=dict(path=str(root),samples=[],success=False)
def fetch(path):
    with urllib.request.urlopen('http://127.0.0.1:3090'+path,timeout=1) as f:return json.load(f)
try:
    publisher=EncoderPublisher()
    with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,vision_publisher=publisher) as rig:
        try:
            rig.stop();info=rig.get_info();report['initial_info']=asdict(info)
            assert info.firmware=='executor-v4-rehome' and info.encoder_upright_raw==370
            started=time.monotonic()
            while time.monotonic()-started<20:
                state=rig.state
                assert not state.enabled and state.mode==0 and state.healthy and state.homed and state.switch_profile and state.fault==0
                assert abs(state.x)<.001 and rig.error is None
                data=fetch('/api/encoder');packet=data.get('packet')
                if packet:
                    assert packet['sdk_state']['sid']==state.sid
                    assert packet['sdk_info']['encoder_upright_raw']==370
                    assert packet['valid'] is True
                    age=time.monotonic()-packet['host_t']
                    assert 0<=age<.2
                    report['samples'].append(dict(receipt_s=time.monotonic(),packet=packet,viewer=data))
                time.sleep(.04)
            assert len(report['samples'])>=100,'missing encoder mirror'
            report['publisher']=dict(error=publisher.error,dropped=publisher.dropped,sequence=publisher.sequence)
            assert publisher.error is None
        finally:
            rig.stop();report['final']=asdict(rig.state);report['final_info']=asdict(rig.get_info())
    time.sleep(.7)
    report['after_close']=fetch('/api/encoder')
    report['camera_after_close']=fetch('/api/state')['comparison']['status']
    report['success']=True
except BaseException as exc:
    report['error']=repr(exc)
finally:
    (root/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2),flush=True)
    print('mirror_samples',len(report['samples']),flush=True)
if not report['success']:raise SystemExit(1)
