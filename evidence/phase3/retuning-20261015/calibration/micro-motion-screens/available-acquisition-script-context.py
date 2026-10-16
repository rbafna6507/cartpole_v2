"""Bounded stopped/micro-motion repeatability experiment; never changes calibration.

One 10mm cart excursion, rehome, and rest. Native STATE, camera geometry,
and explicitly uncommissioned SDK shadow outputs are retained separately.
"""
import argparse
from collections import deque
from dataclasses import asdict
import json
import math
from pathlib import Path
import socket
import statistics
import threading
import time
import urllib.request

from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from cartpole_sdk.sensing.stream import SensingStreamClient, StreamDeadline
from cartpole_sdk.sensing.shadow import ShadowObserver

PORT='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'

def raw_count(theta, reference=370):
    if not math.isfinite(theta):
        raise RuntimeError('nonfinite angle')
    units=theta*4096/math.tau
    nearest=round(units)
    if abs(units-nearest)>.001:
        raise RuntimeError('angle is not the audited native-count STATE encoding')
    return (reference+nearest)%4096

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--direction',type=int,choices=(-1,1),required=True)
    ap.add_argument('--label',required=True)
    a=ap.parse_args()
    if not a.label.replace('-','').replace('_','').isalnum():ap.error('simple label required')
    root=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')/('calibration-screen-'+a.label+'-'+str(time.time_ns()))
    root.mkdir(parents=True)
    report={'path':str(root),'direction':a.direction,'success':False,'reference_changed':False,
            'purpose':'diagnostic repeatability screen; not a labeled upright/hanging training pair',
            'raw_decode':'lossless audited v4 unfiltered theta decode; distinct register-read ticks, not independent ADC conversions'}
    phase='startup';end=threading.Event();latest={};poses=[];states=[];events=[]
    started=time.monotonic();absolute_end=started+50
    config=json.loads(Path('/tmp/proposed-live-shadow-config.json').read_text())
    config['session_id']='calibration-screen-'+a.label+'-'+str(time.time_ns())
    (root/'shadow-config.json').write_text(json.dumps(config,indent=2))
    observer=ShadowObserver(config)
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.setblocking(False)
    def camera():
        after=None;session=None;last_seq=None
        with (root/'source-and-shadow.jsonl').open('w') as log:
            def record(row):log.write(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n')
            record({'type':'configuration','config':config})
            while not end.is_set() and time.monotonic()<absolute_end:
                try:
                    client=SensingStreamClient('http://127.0.0.1:3090/api/sensing-stream',timeout_s=.3)
                    for env,received in client.messages(deadline=absolute_end,after_seq=after,session=session,max_hz=100):
                        if end.is_set():break
                        now=time.monotonic();snap=env['vision'];enc=env['encoder']
                        latest.update(snapshot=snap,receipt=now)
                        if snap.get('seq')!=last_seq:
                            last_seq=snap.get('seq');poses.append({'phase':phase,'received_ns':received,'snapshot':snap})
                        if snap.get('angle_valid') and snap.get('pivot_px') and snap.get('bob_px'):
                            latest.update(good=snap,good_receipt=now)
                        if enc.get('latest_seq') is not None:after=enc['latest_seq'];session=enc.get('session')
                        record({'type':'vision_queued','received_ns':time.monotonic_ns(),'source_received_ns':received,'snapshot':snap,'phase':phase})
                        available=time.monotonic_ns()
                        record({'type':'encoder_batch','received_ns':available,'transport_received_ns':received,'response':enc,'phase':phase})
                        now_ns=time.monotonic_ns();record({'type':'pending_flush','received_ns':now_ns,'phase':phase})
                        if not observer.error:
                            try:
                                observer.enqueue_vision(snap,received_ns=received)
                                observer.encoder_batch(enc,received_ns=available)
                                observer.flush_pending(now_ns=now_ns)
                            except ValueError as exc:
                                # This experiment uses native firmware control and raw
                                # camera geometry. Shadow failure stays invalid and visible;
                                # it never changes calibration or gains or silently reanchors.
                                record({'type':'shadow_error','error':str(exc),'received_ns':time.monotonic_ns()})
                                events.append({'event':'shadow_invalid','error':str(exc)})
                        packet=observer.packet(now_ns=time.monotonic_ns())
                        record({'type':'shadow','packet':packet,'phase':phase})
                        try:udp.sendto(json.dumps(packet,allow_nan=False,separators=(',',':')).encode(),('127.0.0.1',3097))
                        except OSError:pass
                    break
                except StreamDeadline:break
                except OSError as exc:
                    events.append({'event':'camera_transport','error':str(exc),'t':time.monotonic()});end.wait(.05)
                except BaseException as exc:
                    latest['error']=repr(exc);events.append({'event':'source_error','error':repr(exc)});break
    thread=None
    try:
        with Rig(PORT,rate_hz=250,log_dir=root,vision_publisher=EncoderPublisher()) as rig:
            def guard(motion=False):
                s=rig.state
                assert time.monotonic()<absolute_end,'experiment deadline'
                assert not latest.get('error'),('camera/shadow failure',latest.get('error'))
                assert s.healthy and s.homed and s.switch_profile and not s.fault and rig.error is None,'executor health'
                assert time.monotonic_ns()-s.received_ns<100_000_000,'serial freshness'
                assert abs(s.x)<.03 and abs(s.velocity)<.065,'micro-motion envelope'
                if motion:
                    v=latest.get('good',{})
                    assert time.monotonic()-latest.get('good_receipt',0)<.25 and time.monotonic()-v.get('t',0)<.25,'camera freshness/visibility'
                    assert abs(v['pivot_px'][0]-pivot_start)<70,'camera cart displacement'
                    assert abs(s.omega)<4.,'unexpected pole motion'
                return s
            def observe(seconds, *, require_stopped=True):
                until=time.monotonic()+seconds;tick=rig.state.tick
                while time.monotonic()<until:
                    s=rig.wait_state(after_tick=tick,timeout=.12);tick=s.tick;guard()
                    if require_stopped:assert not s.enabled and s.mode==0 and abs(s.x)<.001,'stopped home required'
                    states.append({'phase':phase,'raw_count':raw_count(s.theta),'state':asdict(s)})
            try:
                rig.stop();info=rig.get_info();report['initial_info']=asdict(info)
                assert info.firmware=='executor-v4-rehome' and info.encoder_upright_raw==370
                assert info.encoder_conf_valid and info.encoder_conf==768 and info.i2c_errors==0
                report['parameters_before']=rig.get_parameters();guard()
                assert abs(rig.state.x)<.001 and abs(rig.state.omega)<.2 and abs(rig.state.theta)>2.75,'settled hanging at home required'
                owner_deadline=time.monotonic()+2
                while True:
                    with urllib.request.urlopen('http://127.0.0.1:3090/api/encoder',timeout=.5) as f:
                        owner=json.load(f).get('packet')
                    if owner and owner['sdk_state']['sid']==rig.state.sid and owner.get('sdk_info'):break
                    assert time.monotonic()<owner_deadline,'current encoder owner was not published'
                    time.sleep(.02)
                thread=threading.Thread(target=camera,daemon=True);thread.start()
                ready=time.monotonic()+3
                while not latest.get('good'):
                    assert time.monotonic()<ready,('camera start',latest)
                    time.sleep(.02)
                pivot_start=latest['good']['pivot_px'][0]
                phase='baseline';observe(5.)
                assert abs(rig.state.omega)<.2 and abs(rig.state.theta)>2.75,'pole must remain settled before motion'
                guard(motion=True);phase='excursion';origin=rig.state.x
                rig.start('manual',2.);move_end=time.monotonic()+1.2
                while a.direction*(rig.state.x-origin)<.008:
                    guard(motion=True);assert time.monotonic()<move_end,'excursion deadline'
                    rig.set_velocity(a.direction*.03,50)
                    s=rig.state;states.append({'phase':phase,'raw_count':raw_count(s.theta),'state':asdict(s)})
                    time.sleep(.01)
                brake_end=time.monotonic()+.4
                rig.set_velocity(0.,50)
                while abs(rig.state.velocity)>.001 or abs(rig.state.acceleration)>.02:
                    guard(motion=True);assert time.monotonic()<brake_end,'braking deadline'
                    rig.set_velocity(0.,50);time.sleep(.01)
                rig.stop();report['excursion_end']=asdict(rig.state)
                phase='rehome';guard(motion=True);rig.rehome()
                home_end=time.monotonic()+5.5
                while rig.state.enabled:
                    guard(motion=True);assert time.monotonic()<home_end,'rehome deadline';time.sleep(.01)
                rig.stop();assert abs(rig.state.x)<.001,'return missed home'
                phase='settling';quiet=deque();settle_end=time.monotonic()+15
                while True:
                    observe(.05);s=rig.state;now=time.monotonic();quiet.append((now,s.theta,s.omega))
                    while quiet and now-quiet[0][0]>1:quiet.popleft()
                    if len(quiet)>10 and now-quiet[0][0]>.8 and max(abs(q[2]) for q in quiet)<.12 and max(q[1] for q in quiet)-min(q[1] for q in quiet)<.006:break
                    assert now<settle_end,'pole did not settle'
                guard(motion=True);phase='after';observe(5.)
                report['parameters_after']=rig.get_parameters()
                assert report['parameters_before']==report['parameters_after'],'unexpected parameter change'
                guard(motion=True)
                assert thread.is_alive(),'camera collector ended early'
                packet=observer.packet(now_ns=time.monotonic_ns())
                report['shadow_diagnostics']=packet['diagnostics']
                report['shadow_valid']=not bool(observer.error)
                report['success']=True
            finally:
                rig.stop();report['final']=asdict(rig.state);report['final_info']=asdict(rig.get_info())
                assert report['final_info']['encoder_upright_raw']==370,'reference changed'
    except BaseException as exc:report['error']=repr(exc);report['success']=False
    finally:
        end.set()
        if thread:thread.join(timeout=1)
        udp.close();report['events']=events
        (root/'states.jsonl').write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in states))
        (root/'vision.jsonl').write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in poses))
        report['summary']={}
        for name in ('baseline','after'):
            ss=[r for r in states if r['phase']==name]
            vv=[r['snapshot'] for r in poses if r['phase']==name and r['snapshot'].get('angle_valid') and r['snapshot'].get('pivot_px') and r['snapshot'].get('bob_px')]
            def cam_angle(v):return math.atan2(v['bob_px'][0]-v['pivot_px'][0],v['bob_px'][1]-v['pivot_px'][1])
            report['summary'][name]={'state_count':len(ss),'camera_count':len(vv),
                'raw_mean':statistics.mean(r['raw_count'] for r in ss) if ss else None,
                'raw_span':max(r['raw_count'] for r in ss)-min(r['raw_count'] for r in ss) if ss else None,
                'encoder_mean':statistics.mean(r['state']['theta'] for r in ss) if ss else None,
                'camera_down_mean':statistics.mean(cam_angle(v) for v in vv) if vv else None,
                'camera_down_std':statistics.pstdev(cam_angle(v) for v in vv) if vv else None,
                'pivot_x_mean':statistics.mean(v['pivot_px'][0] for v in vv) if vv else None}
        report['elapsed_s']=time.monotonic()-started
        (root/'summary.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    if not report['success']:raise SystemExit(1)

if __name__=='__main__':main()
