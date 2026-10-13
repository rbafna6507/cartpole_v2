#!/usr/bin/env python3
"""Record raw encoder readings at 0, 90, 180 and 270 degrees (swingup v15+)."""
import argparse
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path
from cartpole import Link

CPR = 4096
POSES = [(0, 'down'), (90, 'toward +cart (right if +cart moves right)'),
         (180, 'upright'), (270, 'toward -cart (left if +cart moves right)')]


def summarize_pose(angle, samples):
    """Store every reading; spread and diagnostic flags never reject a pose."""
    if not samples:
        raise ValueError('No encoder readings received')
    values = [s['raw'] for s in samples]
    c = sum(math.cos(v*2*math.pi/CPR) for v in values)
    q = sum(math.sin(v*2*math.pi/CPR) for v in values)
    mean = math.atan2(q, c)*CPR/(2*math.pi) % CPR
    deviations = [(v-mean+CPR/2) % CPR-CPR/2 for v in values]
    return dict(reference_deg=angle, raw_mean=mean, raw_values=values,
                sample_count=len(samples), samples=samples,
                raw_std_counts=statistics.pstdev(deviations),
                span_deg=(max(deviations)-min(deviations))*360/CPR)


def wait_until(link, predicate, timeout=1):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if link.rx_error or not link.thread.is_alive():
            raise RuntimeError(f'Serial connection lost: {link.rx_error or "reader stopped"}')
        if predicate():
            return
        time.sleep(.01)
    raise TimeoutError('No readable encoder response received')


def stop_and_wait(link):
    # Boot may spend up to 15 seconds waiting for the pendulum to settle.
    for attempt in range(20):
        sent = time.monotonic()
        link.send('stop')
        link.send('rate 0')
        try:
            wait_until(link, lambda: link.last_stop_ack_at is not None and
                       link.last_stop_ack_at >= sent)
            return
        except TimeoutError:
            if attempt == 19:
                raise TimeoutError('No STOP acknowledgment. Check the port and v15 firmware at 115200 baud.')


def capture(link, angle, count):
    result = []
    for _ in range(count):
        for attempt in range(5):
            with link.lock:
                sequence = link.encoder_sequence
            link.send('enc')
            try:
                wait_until(link, lambda: link.encoder_sequence > sequence)
            except TimeoutError:
                print(f'  Unreadable/missing serial reply; retry {attempt+1}/5.', flush=True)
                continue
            with link.lock:
                sample = dict(link.encoder_samples[-1])
            if sample['enabled']:
                stop_and_wait(link)
                print('  Drivers stopped; requesting the reading again.', flush=True)
                continue
            result.append(sample)
            break
        else:
            raise TimeoutError('No readable encoder value after 5 requests. No value was invented or saved for this position.')
    return summarize_pose(angle, result)


def save_report(path, poses, port, baud, complete=False):
    report = dict(schema=2, created_local=datetime.now().isoformat(), complete=complete,
                  convention='0 down; 90 toward +cart; 180 upright; 270 toward -cart',
                  port=port, baud=baud, poses=poses,
                  calibration=dict(raw_counts_per_turn=CPR, points=[
                      dict(reference_deg=p['reference_deg'], raw=p['raw_mean']) for p in poses]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(report, indent=2)+'\n')
    temporary.replace(path)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', help='ESP32 serial device; autodetect if omitted')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--samples', type=int, default=1, help='readings per position (default: 1)')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    if not 1 <= args.samples <= 500:
        ap.error('--samples must be 1–500')
    output = args.output or Path('encoder_calibration')/f'encoder_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
    if output.exists():
        ap.error(f'Output already exists: {output}')
    print('Close other serial programs. Drivers will be disabled; support the height assembly.')
    print('Place the pendulum at each reference and press Enter to record its raw value.')
    print(f'Recordings: {output.resolve()}', flush=True)
    link = None
    poses = []
    try:
        link = Link(args.port, args.baud, logdir=str(output.parent/'sessions'), reconnect=False, verbose=False)
        save_report(output, poses, link.port_name, args.baud)
        stop_and_wait(link)
        for angle, label in POSES:
            while True:
                answer = input(f'\n{angle}° — {label}. Enter to record; q to quit: ').strip().lower()
                if answer in ('q', 'quit'):
                    raise KeyboardInterrupt
                try:
                    pose = capture(link, angle, args.samples)
                except TimeoutError as exc:
                    print(f'  {exc}\n  Still at {angle}°; press Enter to retry.', flush=True)
                    continue
                poses.append(pose)
                save_report(output, poses, link.port_name, args.baud, complete=len(poses)==4)
                print(f"  SAVED {angle}° = {pose['raw_mean']:.3f} counts", flush=True)
                if any(not s['valid'] for s in pose['samples']):
                    print('  Encoder marked this reading invalid/stale; its raw value and flags were saved.')
                break
        print('\nRecorded calibration points:')
        for pose in poses:
            print(f"  {pose['reference_deg']:3}° = {pose['raw_mean']:.3f} counts")
        print(f'Saved: {output.resolve()}\nThese reference values are recorded; firmware correction is not automatically applied.')
    except (KeyboardInterrupt, EOFError):
        print(f'\nStopped. {len(poses)}/4 positions saved at {output.resolve()}.')
    except (RuntimeError, TimeoutError, OSError) as exc:
        print(f'\nRECORDING ERROR: {exc}\n{len(poses)}/4 positions saved at {output.resolve()}.', flush=True)
        raise SystemExit(1)
    finally:
        if link is not None:
            link.close()


if __name__ == '__main__':
    main()
