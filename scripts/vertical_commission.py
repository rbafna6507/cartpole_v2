#!/usr/bin/env python3
"""Standalone operator-attended Z test client; never speaks the cartpole protocol."""
import argparse
import json
import math
from pathlib import Path
import shlex
import threading
import time

HELP = """Commands (nothing moves automatically):
  probe left + [mm]        raw DIR-HIGH probe, then stops holding
  probe left - [mm]        raw DIR-LOW probe; optional distance >0..20 mm
  probe right + [mm]       likewise for other end; default 0.5 mm; max 2 mm/s
  direction left +         confirm + probe moved UP; use - if - moved UP
  direction right +        independently confirm this motor's UP polarity
  home                     explicit prompt, then 40 mm/s DOWN for 5 seconds
  reference                declare current BOTH-bottom pose, or confirm after home
  sine [A Hz center sec]   default: sine 20 1 25 10; smooth approach + 2 s ramps
  status                   print current counted positions/state
  stop                     stop pulses; keep holding torque; invalidate reference
  clear                    acknowledge fault, requiring a new reference
  disable                  explicit supported-rail prompt; disables ALL drivers
  help / quit              quit stops pulses but does NOT release holding torque
Positions are issued pulse counts, NOT measured screw positions.
"""

def motion_command(text):
    """Validate the non-interactive subset; physical acknowledgments are separate."""
    words=shlex.split(text)
    if not words: return None
    if words[0] in ('status','stop','clear') and len(words)==1:return words[0]
    if words[0] in ('probe','direction') and len(words)==3 and words[1] in ('left','right') and words[2] in ('+','-'):
        return ' '.join(words)
    if words[0]=='probe' and len(words)==4 and words[1] in ('left','right') and words[2] in ('+','-'):
        distance=float(words[3])
        if not math.isfinite(distance) or not 0<distance<=20:raise ValueError('Probe distance must be >0 and <=20 mm')
        return ' '.join(words[:3])+f' {distance:.9g}'
    if words[0]=='sine':
        if len(words)==1:words=['sine','20','1','25','10']
        if len(words)!=5:raise ValueError('Use sine AMPLITUDE_MM HZ CENTER_MM SECONDS')
        values=[float(x) for x in words[1:]]
        if not all(math.isfinite(x) for x in values):raise ValueError('Finite values required')
        return 'sine '+' '.join(format(x,'.9g') for x in values)
    raise ValueError('Unknown command; use help')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True,help='Teensy stable serial device path')
    parser.add_argument('--travel-mm',type=float,default=200,help='Usable vertical stroke; owner-confirmed default 200 mm')
    parser.add_argument('--lead-mm',type=float,default=5,help='Travel per screw revolution, default 5 mm (lead, not thread spacing for multi-start screws)')
    parser.add_argument('--motor-steps',type=int,choices=(200,400),default=200,help='200 for 1.8 degrees; 400 for 0.9 degrees; verify motor label')
    parser.add_argument('--microsteps',type=int,choices=(1,2,4,8,16),default=16,help='Must match hardware; unconnected Big Easy Driver MS pins default to 16')
    parser.add_argument('--bottom-stops-rated',action='store_true',help='Declare bottom stops and structure suitable for timed motor bottoming; enables home prompt')
    parser.add_argument('--log',type=Path,help='New JSONL transcript path; default runs/vertical-<timestamp>.jsonl')
    args=parser.parse_args()
    if not math.isfinite(args.travel_mm) or not 10<=args.travel_mm<=500:parser.error('travel must be 10..500 mm')
    if not math.isfinite(args.lead_mm) or not 1<=args.lead_mm<=20:parser.error('lead must be 1..20 mm')
    import serial
    path=args.log or Path('runs')/f'vertical-{time.time_ns()}.jsonl'
    path.parent.mkdir(parents=True,exist_ok=True)
    done=threading.Event();lock=threading.Lock();log_lock=threading.Lock()
    with path.open('x') as log, serial.Serial(args.port,115200,timeout=.1,write_timeout=.2,exclusive=True) as port:
        def record(kind,text):
            with log_lock:
                log.write(json.dumps({'monotonic_ns':time.monotonic_ns(),'kind':kind,'text':text})+'\n');log.flush()
        def send(text):
            with lock:port.write((text+'\n').encode('ascii'))
            if text!='ping':record('tx',text)
        # Refuse production cartpole firmware. No motion or configuration before ID.
        send('hello');deadline=time.monotonic()+3;identified=False
        while time.monotonic()<deadline:
            line=port.readline().decode('ascii',errors='replace').strip()
            if line:record('rx',line)
            if line=='VERTICAL-COMMISSIONING-1':identified=True;break
        if not identified:raise RuntimeError('Standalone firmware not found; no motion requested. Flash the reviewed test sketch first.')
        send('stop');send('ping')
        send(f'configure {args.travel_mm:g} {args.lead_mm:g} {args.motor_steps} {args.microsteps} {int(args.bottom_stops_rated)}')
        deadline=time.monotonic()+2;configured=False
        while time.monotonic()<deadline:
            line=port.readline().decode('ascii',errors='replace').strip()
            if line:record('rx',line);print(line)
            if line.startswith('OK configured'):configured=True;break
            if line.startswith('ERR'):raise RuntimeError(line)
        if not configured:raise RuntimeError('Configuration not acknowledged')
        def heartbeat():
            try:
                while not done.wait(.05):send('ping')
            except Exception as exc:
                done.set();print(f'Heartbeat failed: {type(exc).__name__}; firmware stops pulses after 500 ms, retaining holding torque.')
        def receive():
            try:
                while not done.is_set():
                    line=port.readline().decode('ascii',errors='replace').strip()
                    if line:record('rx',line);print('\n'+line,flush=True)
            except Exception as exc:
                done.set();print(f'Serial receive failed: {type(exc).__name__}')
        threads=[threading.Thread(target=heartbeat,daemon=True),threading.Thread(target=receive,daemon=True)]
        for thread in threads:thread.start()
        print(HELP);print(f'Transcript: {path.resolve()}')
        print('Keep the rail mechanically supported for commissioning; boot/power loss releases drivers.')
        try:
            while not done.is_set():
                text=input('vertical> ').strip()
                if text=='quit':break
                if text=='help':print(HELP);continue
                if text=='home':
                    if not args.bottom_stops_rated:print('Home disabled: confirm mechanical suitability before using --bottom-stops-rated.');continue
                    print('Will command both screws DOWN at 40 mm/s for 5 s (200 mm commanded). No contact/current sensing; no automatic squaring.')
                    if input('Type BOTTOM to execute: ').strip()=='BOTTOM':send('bottom 40 5 CONTACT_OK')
                elif text=='reference':
                    if input('Both ends physically at their bottom references and level? Type BOTH: ').strip()=='BOTH':send('reference CONFIRM')
                elif text=='disable':
                    if input('Rail supported against falling? This releases ALL three drivers. Type SUPPORTED: ').strip()=='SUPPORTED':send('disable SUPPORTED')
                else:
                    try:
                        command=motion_command(text)
                        if command:send(command)
                    except ValueError as exc:print(exc)
        except (EOFError,KeyboardInterrupt):pass
        finally:
            try:send('stop')
            except Exception:pass
            done.set()
            for thread in threads:thread.join(timeout=.5)
            print('\nSTOP requested; heartbeat timeout also stops pulses. Holding torque is retained while powered; no automatic disable.')
    return 0

if __name__=='__main__':raise SystemExit(main())
