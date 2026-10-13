#!/usr/bin/env python3
"""Local cart frequency-test GUI. Run: python3 frequency_test_gui.py

Requires pyserial. Flash frequency_test/frequency_test.ino first.
No serial port is opened until Connect is clicked. --demo uses no hardware.
"""
import argparse
from collections import deque
import csv
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import queue
import secrets
import threading
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
MAX_SPEED = 2.34375
MAX_TRAVEL = 270.0


def waveform(travel, hz, t, finish_at=-1, ramp=2.0):
    if t <= 0:
        return [0.0]*4
    finishing = finish_at >= 0 and t >= finish_at
    u = (t-finish_at)/ramp if finishing else t/ramp
    e, d1, d2, d3 = 1.0, 0.0, 0.0, 0.0
    if finishing and u >= 1:
        return [0.0]*4
    if u < 1:
        e = u**3*(10+u*(-15+6*u))
        d1 = 30*u*u*(1-u)**2/ramp
        d2 = 60*u*(1-u)*(1-2*u)/ramp**2
        d3 = (60-360*u+360*u*u)/ramp**3
        if finishing:
            e, d1, d2, d3 = 1-e, -d1, -d2, -d3
    w, a = 2*math.pi*hz, travel/2000
    s, c = math.sin(w*t), math.cos(w*t)
    return [a*e*s, a*(d1*s+e*w*c), a*(d2*s+2*d1*w*c-e*w*w*s),
            a*(d3*s+3*d2*w*c-3*d1*w*w*s-e*w**3*c)]


def describe(travel, hz, ramp=2.0):
    travel, hz, ramp = float(travel), float(hz), float(ramp)
    if not all(math.isfinite(v) for v in (travel,hz,ramp)):
        raise ValueError('Enter finite numbers for travel, frequency and ramp.')
    if not 1 <= travel <= 1000 or not .02 <= hz <= 5:
        raise ValueError('Preview range: 1–1000 mm and 0.02–5 Hz.')
    if not .5 <= ramp <= 30:
        raise ValueError("Ramp must be 0.5–30 seconds.")
    w, a = 2*math.pi*hz, travel/2000
    speed_bound = a*(w+1.875/ramp)
    problems = []
    if travel > MAX_TRAVEL:
        problems.append('300 mm physical travel minus 15 mm at each end allows 270 mm peak-to-peak. Reduce total travel to run.')
    if speed_bound > MAX_SPEED:
        problems.append('The waveform including its ramp exceeds the 2.34375 m/s pulse ceiling. Reduce frequency or travel.')
    duration = ramp+3/hz
    times=sorted(set([i*duration/800 for i in range(801)]+[i*ramp/200 for i in range(201)]))
    samples=[[t,*waveform(travel,hz,t,ramp=ramp)] for t in times]
    return dict(travel_mm=travel, hz=hz, ramp_s=ramp, period_s=1/hz,
                speed_peak=a*w, acceleration_peak=a*w*w, jerk_peak=a*w**3,
                rpm_peak=a*w*500, speed_bound=speed_bound, errors=problems,
                duration_s=duration,
                samples=samples, preview_peaks=[max(abs(p[k]) for p in samples) for k in range(1,5)])


class Bench:
    """One serial owner, explicit run commands, independent browser/board leases."""
    def __init__(self, demo=False, logdir=None, serial_factory=None):
        self.demo = demo
        self.logdir = Path(logdir or ROOT/'logs/frequency_test')
        self.serial_factory = serial_factory
        self.lock = threading.RLock()
        self.jobs = queue.Queue()
        self.halt = threading.Event()
        self.thread = None
        self.connected = self.ready = False
        self.state = 'DISCONNECTED'
        self.centered = False
        self.last_rx = 0.0
        self.browser_seen = 0.0
        self.messages = deque(maxlen=12)
        self.points = deque(maxlen=3000)
        self.trial = None
        self.diagnostics = {}
        self.logpath = None
        self.start_time = 0.0
        self.finish_at = -1
        self.serial = None
        self.pending = None
        self.csv_file = self.event_file = None

    def note(self, text):
        self.messages.append(text)
        if self.event_file:
            self.event_file.write(json.dumps(dict(host_time_s=time.time(), text=text))+'\n')

    def connect(self, port):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Already connected. Disconnect first.')
            self.ready = self.centered = False
            self.points.clear()
            self.trial = None
            self.diagnostics = {}
            self.last_rx = 0
            self.state = 'CONNECTING'
            self.halt.clear()
            self.jobs = queue.Queue()
            self.browser_seen = time.monotonic()
            self.thread = threading.Thread(target=self._worker,args=(port,),daemon=True)
            self.thread.start()

    def close(self):
        self.halt.set()
        if self.thread:
            self.thread.join(timeout=3)

    def heartbeat(self):
        with self.lock:
            self.browser_seen = time.monotonic()

    def command(self, command, travel=None, hz=None, ramp=2.0):
        with self.lock:
            fresh = time.monotonic()-self.last_rx < .5
            if command != 'stop' and (not self.ready or not fresh):
                raise ValueError('Connect to frequency-test firmware and wait for fresh telemetry.')
            if command == 'run':
                config = describe(travel,hz,ramp)
                if config['errors']:
                    raise ValueError(' '.join(config['errors']))
                if self.state != 'IDLE' or not self.centered:
                    raise ValueError('Stop and confirm the cart is physically centered first.')
                wire = f'run {config["travel_mm"]:.6f} {config["hz"]:.6f} {config["ramp_s"]:.6f}'
            elif command == 'center':
                if self.state not in ('IDLE','FAULT'):
                    raise ValueError('Stop before setting the center.')
                wire, config = 'center', None
            elif command in ('stop','finish'):
                wire, config = command, None
            else:
                raise ValueError('Unknown action.')
            if not self.connected:
                raise ValueError('Not connected.')
            # Browser lease must be present even for a directly submitted Run.
            if command == 'run' and time.monotonic()-self.browser_seen > .75:
                raise ValueError('Browser heartbeat expired.')
            job = dict(wire=wire, config=config, event=threading.Event(), error=None)
            if command == 'stop':
                if self.pending:
                    self.pending['error']='Cancelled by Stop.'
                    self.pending['event'].set()
                    self.pending=None
                while not self.jobs.empty():
                    cancelled=self.jobs.get_nowait()
                    cancelled['error']='Cancelled by Stop.'
                    cancelled['event'].set()
            self.jobs.put(job)
        if not job['event'].wait(2):
            self.halt.set()  # do not leave a delayed Run queued after an HTTP timeout
            raise ValueError('Board did not acknowledge. Connection stopped; check firmware and port.')
        if job['error']:
            raise ValueError(job['error'])

    def _ack(self, line):
        job = self.pending
        if not job:
            return
        command = job['wire'].split()[0]
        expected = {'run':'# RUN ', 'center':'# CENTERED', 'finish':'# FINISH requested', 'stop':'# STOP'}[command]
        if line.startswith('!') or line.startswith(expected):
            if line.startswith('!'):
                job['error'] = line
            elif command == 'run':
                self.trial = job['config']
                self.points.clear()
                self.start_time = time.monotonic()
                self.finish_at = -1
            job['event'].set()
            self.pending = None

    def _parse(self, line):
        if line.startswith('# FREQUENCY_TEST_V1 '):
            self.ready=False
            if not any('Update required' in m for m in self.messages):
                self.note('Update required: flash frequency-test V2 for configurable ramp and diagnostics.')
        elif line.startswith('# FREQUENCY_TEST_V2 '):
            # Reject incompatible drive geometry instead of drawing the wrong scale.
            values = dict(p.split('=',1) for p in line.split()[2:])
            if abs(float(values['max_speed'])-MAX_SPEED)>1e-5 or float(values['max_travel_mm'])!=MAX_TRAVEL:
                raise ValueError('Firmware geometry differs from this GUI.')
            self.ready = True
            self.note('Frequency-test firmware ready.')
        elif line.startswith('D '):
            parts=line.split()
            if len(parts)==9:
                keys=('board_ms','update_hz','max_update_us','timer_hz','max_timer_gap_us','min_step_high_us','min_step_low_us','step_hz')
                values=[float(v) for v in parts[1:]]
                if all(math.isfinite(v) for v in values):
                    self.diagnostics=dict(zip(keys,values))
                    if self.event_file:
                        self.event_file.write(json.dumps(dict(host_time_s=time.time(),diagnostics=self.diagnostics))+'\n')
        elif line.startswith('F '):
            parts = line.split()
            if len(parts)!=11 or parts[2] not in ('IDLE','RAMP_UP','RUNNING','RAMP_DOWN','FAULT'):
                return
            numbers = [float(p) for p in parts[3:]]
            if not all(math.isfinite(p) for p in numbers):
                return
            self.state, self.centered = parts[2], bool(int(parts[-1]))
            self.last_rx = time.monotonic()
            # t, x, v, a, j, pulse-inferred x, pulse-rate v
            self.points.append(numbers[:7])
            self.csv_writer.writerow([time.time(),float(parts[1]),self.state,*numbers])
        elif line.startswith(('#','!')):
            self.note(line)
        self._ack(line)

    def _demo_step(self):
        if self.state in ('RAMP_UP','RUNNING','RAMP_DOWN'):
            t = time.monotonic()-self.start_time
            ramp = self.trial['ramp_s']
            values = waveform(self.trial['travel_mm'],self.trial['hz'],t,self.finish_at,ramp=ramp)
            if self.finish_at>=0 and t>=self.finish_at+ramp:
                self.state, self.centered = 'IDLE', True
            else:
                self.state = 'RAMP_DOWN' if self.finish_at>=0 and t>=self.finish_at else 'RAMP_UP' if t<ramp else 'RUNNING'
            self._parse(f'F {int(t*1000)} {self.state} {t} '+ ' '.join(map(str,values))+f' {values[0]} {values[1]} {int(self.centered)}')
        else:
            self.last_rx = time.monotonic()

    def _worker(self, port):
        try:
            if not self.demo:
                if self.serial_factory is None:
                    import serial
                    self.serial_factory = serial.Serial
                self.serial = self.serial_factory(port,921600,timeout=.01,write_timeout=.1,exclusive=True)
            self.logdir.mkdir(parents=True,exist_ok=True)
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            self.logpath = str(self.logdir/f'frequency_{stamp}.csv')
            self.csv_file = open(self.logpath,'w',newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(['host_time_s','board_ms','state','test_time_s','reference_x_m','reference_v_m_s','reference_a_m_s2','reference_j_m_s3','pulse_inferred_x_m','commanded_v_m_s','center_confirmed'])
            self.event_file = open(self.logdir/f'frequency_{stamp}_events.jsonl','w',buffering=1)
            self.note('DEMO: no hardware' if self.demo else f'Connected {port}; x is pulse-inferred, not measured cart position.')
            self.connected = True
            if self.demo:
                self.ready = True
                self.state = 'IDLE'
                self.last_rx = time.monotonic()
            last_ping = last_hello = last_flush = 0
            lease_stopped = False
            while not self.halt.is_set():
                now = time.monotonic()
                with self.lock:
                    lease_ok = now-self.browser_seen < .75 and (not self.ready or now-self.last_rx < .75)
                    if not lease_ok and not lease_stopped:
                        if self.serial:
                            self.serial.write(b'stop\n')
                        self.state, self.centered = 'IDLE', False
                        self.note('Browser/telemetry heartbeat expired; STOP sent.')
                        lease_stopped = True
                    if lease_ok:
                        lease_stopped = False
                        if self.serial and now-last_ping>.1:
                            self.serial.write(b'ping\n'); last_ping=now
                    if self.serial and not self.ready and now-last_hello>.5:
                        self.serial.write(b'hello\n');last_hello=now
                    if self.pending is None:
                        try:
                            job = self.jobs.get_nowait()
                        except queue.Empty:
                            job = None
                        if job:
                            if not lease_ok and job['wire'].startswith('run '):
                                job['error']='Browser heartbeat expired.';job['event'].set()
                            else:
                                self.pending=job;self.note('TX '+job['wire'])
                                if self.serial:
                                    self.serial.write((job['wire']+'\n').encode())
                                else:
                                    cmd=job['wire'].split()[0]
                                    if cmd=='run': self._ack('# RUN demo');self.state='RAMP_UP'
                                    elif cmd=='center': self.centered=True;self.state='IDLE';self._ack('# CENTERED')
                                    elif cmd=='stop': self.state='IDLE';self.centered=False;self._ack('# STOP')
                                    elif cmd=='finish':
                                        self.finish_at=max(now-self.start_time,self.trial['ramp_s']) if self.trial else -1
                                        self._ack('# FINISH requested')
                if self.serial:
                    raw=self.serial.readline()
                    if raw:
                        with self.lock:
                            try:
                                self._parse(raw.decode('utf8','replace').strip())
                            except (ValueError,KeyError) as exc:
                                self.note('Malformed/incompatible board message: '+str(exc))
                else:
                    with self.lock: self._demo_step()
                    time.sleep(.02)
                if now-last_flush>1:
                    self.csv_file.flush();last_flush=now
        except Exception as exc:
            with self.lock: self.note('Connection error: '+str(exc))
        finally:
            if self.serial:
                try: self.serial.write(b'stop\n')
                except Exception: pass
                self.serial.close(); self.serial=None
            with self.lock:
                self.connected=self.ready=self.centered=False
                self.state='DISCONNECTED'
                if self.pending:
                    self.pending['error']='Connection closed.';self.pending['event'].set();self.pending=None
                while not self.jobs.empty():
                    job=self.jobs.get_nowait();job['error']='Connection closed.';job['event'].set()
                for f in (self.csv_file,self.event_file):
                    if f: f.close()
                self.csv_file=self.event_file=None

    def snapshot(self):
        with self.lock:
            return dict(demo=self.demo,connected=self.connected,ready=self.ready,state=self.state,
                        centered=self.centered,fresh=time.monotonic()-self.last_rx<.5,
                        messages=list(self.messages),points=list(self.points),trial=self.trial,logpath=self.logpath,diagnostics=dict(self.diagnostics))


def make_server(bench, port=8766):
    token = secrets.token_urlsafe(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def respond(self,status,body,content_type='application/json'):
            data = body.encode() if isinstance(body,str) else json.dumps(body,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError): pass
        def do_GET(self):
            # Host check prevents arbitrary websites reaching this local control server via DNS rebinding.
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
                return self.respond(403,{'error':'Local host only.'})
            if self.path=='/':
                html=(ROOT/'frequency_test/index.html').read_text().replace('__TOKEN__',token)
                return self.respond(200,html,'text/html; charset=utf-8')
            if self.path=='/api/state': return self.respond(200,bench.snapshot())
            if self.path=='/api/ports':
                from serial.tools import list_ports
                return self.respond(200,[dict(device=p.device,description=p.description) for p in list_ports.comports()])
            return self.respond(404,{'error':'Not found'})
        def do_POST(self):
            if self.headers.get('X-Bench-Token')!=token:
                return self.respond(403,{'error':'Reload the local test page.'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<4096: raise ValueError('Invalid request size.')
                body=json.loads(self.rfile.read(length))
                if self.path=='/api/heartbeat': bench.heartbeat()
                elif self.path=='/api/preview': return self.respond(200,describe(body['travel'],body['hz'],body.get('ramp',2.0)))
                elif self.path=='/api/connect': bench.connect(body.get('port'))
                elif self.path=='/api/disconnect': bench.close()
                elif self.path=='/api/action':
                    if body.get('command')=='center' and body.get('confirmed') is not True:
                        raise ValueError('Confirm the cart is physically at the center.')
                    bench.command(body['command'],body.get('travel'),body.get('hz'),body.get('ramp',2.0))
                else: return self.respond(404,{'error':'Not found'})
                self.respond(200,{'ok':True})
            except (ValueError,KeyError,TypeError) as exc:
                self.respond(400,{'error':str(exc)})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true',help='Simulated plots and controls, no serial access')
    parser.add_argument('--port',type=int,default=8766,help='Local web server port, not serial port')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    bench=Bench(demo=args.demo)
    server=make_server(bench,args.port)
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'Frequency test: {url}'+(' — DEMO, no hardware' if args.demo else ''),flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: bench.close();server.server_close()


if __name__=='__main__': main()
