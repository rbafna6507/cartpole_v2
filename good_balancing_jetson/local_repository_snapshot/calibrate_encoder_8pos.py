#!/usr/bin/env python3
"""Record eight physical pendulum angles and a return-to-down repeatability check."""
from passive_capture import parser,prompt,run_session,calibration_summary


def collect(session,seconds):
    print('\nChoose one viewing side and keep it throughout. Angles increase CLOCKWISE from hanging DOWN.')
    print('Use a physical angle guide/protractor; do not position from the encoder reading.')
    print('Hold each pose still until SAVED appears. These measurements do not change firmware calibration.')
    session.report['convention']='0 down; clockwise from down, viewed consistently from operator-selected side'
    session.report['viewing_side']=input('Describe the viewing side (e.g. looking at sensor board): ').strip()
    session.save()
    labels=['down','45 degrees clockwise from down','horizontal, 90 degrees clockwise from down',
            '135 degrees clockwise from down','upright','225 degrees clockwise from down',
            'horizontal, 270 degrees clockwise from down','315 degrees clockwise from down','down again after one full turn']
    poses=[]
    for i,label in enumerate(labels):
        prompt(f'\nPosition {i+1}/9: {label}. Hold still')
        phase=session.capture(f'pose_{i*45:03d}',seconds,reference_deg=i*45)
        poses.append(phase)
        s=phase['summary']
        print(f"SAVED {i*45:3d}°: raw mean {s['raw_mean']:.2f}, spread {s['span_counts']*360/4096:.2f}°, {s['sample_count']} samples",flush=True)
    result=calibration_summary(poses);session.report['calibration_summary']=result;session.save()
    print(f"Return-to-down difference: {result['closure_error_deg']:.2f}°")
    print(f"Measured upright raw count: {result['upright_raw_measured']:.2f}; NOT applied.")
    for warning in result['warnings']:print('REVIEW:',warning)


def main():
    p=parser(__doc__);p.add_argument('--seconds',type=float,default=2,help='Seconds held per pose (default 2)')
    args=p.parse_args()
    if not .5<=args.seconds<=10:p.error('--seconds must be between 0.5 and 10')
    return run_session('encoder_8pos',args,lambda s:collect(s,args.seconds))

if __name__=='__main__':raise SystemExit(main())
