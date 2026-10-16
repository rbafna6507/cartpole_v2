"""Stopped, bounded live SDK observation/fusion wiring test. No policy or motion."""
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from cartpole_sdk.sensing.shadow import ShadowObserver
from cartpole_sdk.recording import canonical_json
from dataclasses import asdict
from pathlib import Path
import json,time,urllib.request,socket,statistics
root=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')/('sdk-shadow-live-'+str(time.time_ns()))
root.mkdir(parents=True)
config=json.loads(Path('/tmp/proposed-live-shadow-config.json').read_text())
config['session_id']='stopped-live-shadow-'+str(time.time_ns())
(root/'configuration.json').write_text(json.dumps(config,indent=2))
observer=ShadowObserver(config);udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.setblocking(False)
report=dict(path=str(root),success=False,counts={},last=None)
def fetch(path):
    with urllib.request.urlopen('http://127.0.0.1:3090'+path,timeout=.5) as f:return json.load(f)
try:
    with (root/'capture.jsonl').open('w') as capture:
        capture.write(canonical_json(dict(type='configuration',config=config))+'\n')
        with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,vision_publisher=EncoderPublisher()) as rig:
            try:
                rig.stop();info=rig.get_info();report['initial_info']=asdict(info)
                assert info.firmware=='executor-v4-rehome' and info.encoder_upright_raw==370
                started=time.monotonic()
                while time.monotonic()-started<25:
                    state=rig.state
                    assert not state.enabled and state.mode==0 and state.healthy and state.homed and state.switch_profile and not state.fault
                    assert abs(state.x)<.001 and rig.error is None
                    packet=fetch('/api/encoder').get('packet');now=time.monotonic_ns()
                    if not packet or packet['sdk_state']['sid']!=state.sid:continue
                    capture.write(canonical_json(dict(type='encoder',packet=packet,received_ns=now))+'\n')
                    observer.encoder(packet,received_ns=now)
                    snapshot=fetch('/api/state');now=time.monotonic_ns()
                    assert snapshot['camera']['settings']['actual_frame_size']==[960,600]
                    assert snapshot['camera']['settings']['rotation']==180
                    capture.write(canonical_json(dict(type='vision',snapshot=snapshot,received_ns=now))+'\n')
                    observer.vision(snapshot,received_ns=now)
                    result=observer.packet(now_ns=time.monotonic_ns())
                    capture.write(canonical_json(dict(type='shadow',packet=result))+'\n')
                    udp.sendto(canonical_json(result).encode(),('127.0.0.1',3097))
                    status=result['diagnostics']['status'];report['counts'][status]=report['counts'].get(status,0)+1
                    report['last']=result
                    time.sleep(.008)
                report['viewer']=fetch('/api/sdk-state')
                assert observer.fusion.accepted_vision>20
                report['success']=True
            finally:
                rig.stop();report['final']=asdict(rig.state);report['final_info']=asdict(rig.get_info())
        # No new encoder or camera updates: explicit stale invalidation must reach viewer.
        time.sleep(.4)
        packet=observer.packet(now_ns=time.monotonic_ns())
        report['after_close']=packet
        udp.sendto(canonical_json(packet).encode(),('127.0.0.1',3097))
        fused=[s for s in packet['observation']['samples'] if s['source']=='fused']
        assert fused and all(s['validity']=='invalid' for s in fused)
except BaseException as exc:report['success']=False;report['error']=repr(exc)
finally:
    udp.close();(root/'summary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
if not report['success']:raise SystemExit(1)
