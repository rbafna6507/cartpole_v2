"""Shared passive acquisition for the existing Teensy cartpole firmware.

Only pyserial and the adjacent cartpole.py / angle_plot.py are required.
No calibration, home, motor enable or motion command is sent.
"""
import argparse
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path
from cartpole import Link

DEFAULT_PORT='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
CPR=4096


def atomic_json(path, value):
    path=Path(path)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    tmp.replace(path)


def circular_delta(a,b):
    return (a-b+CPR/2)%CPR-CPR/2


def circular_summary(values):
    if not values:raise ValueError('No encoder samples')
    c=sum(math.cos(v*2*math.pi/CPR) for v in values)
    s=sum(math.sin(v*2*math.pi/CPR) for v in values)
    mean=math.atan2(s,c)*CPR/(2*math.pi)%CPR
    deviations=[circular_delta(v,mean) for v in values]
    return dict(sample_count=len(values),raw_mean=mean,
                raw_std_counts=statistics.pstdev(deviations),
                span_counts=max(deviations)-min(deviations))


def calibration_summary(poses):
    if len(poses)<9:return {'status':'incomplete; eight poses and down recheck required'}
    raw=[p['summary']['raw_mean'] for p in poses]
    increments=[circular_delta(b,a) for a,b in zip(raw,raw[1:])]
    direction=1 if sum(increments)>=0 else -1
    unwrapped=[0.0]
    for step in increments:unwrapped.append(unwrapped[-1]+step)
    residual=[direction*v*360/CPR-p['reference_deg'] for v,p in zip(unwrapped,poses)]
    closure=circular_delta(raw[-1],raw[0])*360/CPR
    warnings=[]
    if abs(closure)>3:warnings.append('Down reference did not repeat within 3 degrees.')
    if any(direction*x<=0 for x in increments):warnings.append('Raw angle is not monotonic through the requested positions.')
    if max(abs(x) for x in residual)>5:warnings.append('Offset-only mapping has residuals over 5 degrees; review placement, repeatability and sensor geometry.')
    if any(p['summary']['span_counts']*360/CPR>2 for p in poses):warnings.append('At least one held pose moved over 2 degrees during capture.')
    return dict(direction=direction,quadrant_note='Direction is relative to the viewing side chosen by the operator, not cart +x.',
                raw_steps=increments,offset_only_residual_deg=residual,
                closure_error_deg=closure,upright_raw_measured=raw[4],
                warnings=warnings,applied_to_firmware=False)


def validate_sample(sample):
    if not 0<=sample['raw']<CPR:raise RuntimeError('Raw encoder count out of range')
    if sample['enabled']:raise RuntimeError('Drivers unexpectedly enabled; STOP requested')
    if not sample['valid']:raise RuntimeError('Encoder reported an invalid/stale reading')
    if not sample['status']&32:raise RuntimeError('Encoder reports no magnet detected')


def parser(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--port',default=DEFAULT_PORT)
    p.add_argument('--output',type=Path,help='New output directory; existing directories are never overwritten')
    return p


def prompt(text):
    answer=input(text+' [Enter to continue, q to quit] ').strip().lower()
    if answer in ('q','quit'):raise KeyboardInterrupt


class PassiveSession:
    def __init__(self,kind,port,output=None):
        self.output=output or Path('experiments')/(kind+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        self.output=Path(self.output)
        self.output.mkdir(parents=True,exist_ok=False)
        self.link=None
        self.report=dict(schema=1,kind=kind,created_local=datetime.now().astimezone().isoformat(),
                         port=port,complete=False,phases=[],parameters={},
                         expected_firmware='swingup-125mm-60t-v33-teensy41',
                         note='Raw E frames and original CRC-checked telemetry retained. E.zero_raw is the relative tick origin, NOT saved upright. No calibration or motion commands sent.')
        self.save()
        print('Output directory:',self.output.resolve(),flush=True)
        try:
            self.link=Link(port,logdir=str(self.output/'serial'),reconnect=False,verbose=False)
            sent=time.monotonic()
            self.send('stop')
            deadline=sent+5
            while self.link.last_stop_ack_at is None or self.link.last_stop_ack_at<sent:
                self.check()
                if time.monotonic()>deadline:raise RuntimeError('No fresh STOP acknowledgment')
                time.sleep(.01)
            self.send('rate 100');self.send('params')
            # Drain the firmware parameter reply before taking a fresh snapshot.
            deadline=time.monotonic()+5
            while not all(k in self.link.params for k in ('serial_crc16','encoder_snapshot','encoder_upright_raw','encoder_reference_saved','cart_steps_per_m')):
                self.check()
                if time.monotonic()>deadline:raise RuntimeError('Firmware parameter/capability response incomplete')
                time.sleep(.01)
            with self.link.lock:self.report['parameters']=dict(self.link.params)
            if self.report['parameters'].get('encoder_snapshot')!=1:raise RuntimeError('Firmware lacks raw encoder snapshots')
            self.sample()
            self.save()
        except BaseException:
            self.close()
            raise

    def send(self,command):
        if command not in ('stop','ping','enc','params','rate 25','rate 100'):
            raise ValueError('Command is not allowed by passive recorder: '+command)
        if not self.link.send(command):raise RuntimeError('Serial write failed')

    def check(self):
        if self.link.rx_error or not self.link.thread.is_alive():
            raise RuntimeError('Serial reader stopped: '+str(self.link.rx_error))

    def sample(self):
        self.check()
        with self.link.lock:seq=self.link.encoder_sequence
        self.send('enc')
        deadline=time.monotonic()+1
        while True:
            self.check()
            with self.link.lock:
                sample=dict(self.link.encoder_samples[-1]) if self.link.encoder_sequence>seq else None
            if sample is not None:
                # Raw bytes and invalid readings are already preserved in serial/events.
                try:validate_sample(sample)
                except RuntimeError:
                    self.send('stop');raise
                previous=getattr(self,'last_board_ms',None)
                if previous is not None:
                    delta=(sample['board_ms']-previous)%2**32
                    if delta==0 or delta>=2**31:
                        raise RuntimeError('Encoder board timestamp repeated or moved backward; possible board reset. Start a new run.')
                self.last_board_ms=sample['board_ms']
                return sample
            if time.monotonic()>deadline:raise RuntimeError('No fresh encoder snapshot within 1 second')
            time.sleep(.002)

    def capture(self,label,seconds,**metadata):
        phase=dict(label=label,file=label+'.jsonl',duration_requested_s=seconds,
                   started_host_time_s=time.time(),complete=False,**metadata)
        self.report['phases'].append(phase);self.save()
        samples=[];start=time.monotonic()
        with (self.output/phase['file']).open('x',buffering=1) as f:
            try:
                while time.monotonic()-start<seconds:
                    tick=time.monotonic();s=self.sample();samples.append(s)
                    f.write(json.dumps(s)+'\n')
                    time.sleep(max(0,.05-(time.monotonic()-tick)))
                if len(samples)<max(2,int(seconds*10)):
                    raise RuntimeError('Too few fresh encoder samples; partial data retained')
                phase['complete']=True
            except BaseException as exc:
                phase['error']=type(exc).__name__+': '+str(exc)
                raise
            finally:
                phase['ended_host_time_s']=time.time()
                if samples:
                    phase['summary']=circular_summary([s['raw'] for s in samples])
                    phase['board_ms_start']=samples[0]['board_ms'];phase['board_ms_end']=samples[-1]['board_ms']
                    gaps=[(b['board_ms']-a['board_ms'])%2**32 for a,b in zip(samples,samples[1:])]
                    phase['max_snapshot_gap_ms']=max(gaps,default=0)
                    phase['i2c_error_counts']=sorted(set(s['i2c_errors'] for s in samples))
                    phase['sensor_status_values']=sorted(set(s['status'] for s in samples))
                self.save()
        return phase

    def save(self):
        atomic_json(self.output/'report.json',self.report)

    def close(self):
        if self.link is not None:
            self.report['bad_serial_frames']=self.link.bad_frames
            self.report['parameters_at_end']=dict(self.link.params)
            try:self.send('rate 25')
            except Exception:pass
            try:self.link.close()
            finally:self.link=None;self.save()


def run_session(kind,args,action):
    session=None
    print('Close cartpole.py and any other serial console first.')
    print('STOP disables ALL motors. Fix the cart and support the height assembly before continuing.')
    try:
        prompt('Ready for passive measurements')
        session=PassiveSession(kind,args.port,args.output)
        print('Saving to:',session.output.resolve(),flush=True)
        action(session)
        session.report['complete']=True;session.save()
        print('Complete. Send the entire output directory, including serial logs.')
    except (KeyboardInterrupt,EOFError):
        print('\nStopped; all measurements collected so far are retained.')
        return 130
    except (RuntimeError,OSError,ValueError) as exc:
        print('\nCAPTURE ERROR:',exc)
        if session is not None:
            session.report['error']=str(exc);session.save()
        return 1
    finally:
        if session is not None:
            session.close()
            print('Saved:',session.output.resolve())
    return 0
