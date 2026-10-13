#!/usr/bin/env python3
"""Guided passive free-decay recordings using the existing Teensy firmware."""
import time
from passive_capture import parser,prompt,run_session


def collect(session,seconds,trials,angle):
    print('\nKeep the cart fixed throughout. Release by hand without pushing; do not touch it during capture.')
    print('Each trial records a down baseline, a timed release, and a final resting baseline.')
    session.report['release_angle_deg_requested']=angle
    session.report['analysis_status']='Raw data collected for later period/damping fitting; no controller coefficients calculated or applied.'
    session.save()
    for trial in range(1,trials+1):
        side='left' if trial%2 else 'right'
        prompt(f'\nTrial {trial}/{trials}: let the arm hang freely and settle')
        session.capture(f'trial_{trial:02d}_down_before',2)
        prompt(f'Lift about {angle:g}° to your {side} from DOWN, hold it, then press Enter for a 3-second release countdown')
        for count in (3,2,1):print(count,flush=True);time.sleep(1)
        release=time.time()
        print('\aRELEASE NOW — leave the pendulum untouched.',flush=True)
        phase=session.capture(f'trial_{trial:02d}_decay',seconds,release_host_time_s=release,
                              release_side=side,requested_amplitude_deg=angle)
        print(f"Capture finished: {phase['summary']['sample_count']} raw snapshots plus 100 Hz telemetry.",flush=True)
        phase['operator_notes']=input('Any push, contact, cart movement, or release timing issue? Enter for none: ').strip()
        session.save()
        prompt('Let the pendulum settle completely down for the final baseline')
        session.capture(f'trial_{trial:02d}_down_after',2)


def main():
    p=parser(__doc__)
    p.add_argument('--seconds',type=float,default=30,help='Free-decay duration per trial (default 30)')
    p.add_argument('--trials',type=int,default=3)
    p.add_argument('--angle',type=float,default=20,help='Approximate manual release angle from DOWN (default 20 degrees)')
    args=p.parse_args()
    if not 10<=args.seconds<=120:p.error('--seconds must be between 10 and 120')
    if not 1<=args.trials<=10:p.error('--trials must be between 1 and 10')
    if not 5<=args.angle<=45:p.error('--angle must be between 5 and 45 degrees')
    return run_session('pendulum_period',args,lambda s:collect(s,args.seconds,args.trials,args.angle))

if __name__=='__main__':raise SystemExit(main())
