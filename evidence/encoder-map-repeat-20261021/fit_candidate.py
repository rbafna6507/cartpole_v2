#!/usr/bin/env python3
"""Fit a descriptive cyclic camera/encoder model and independently challenge it.

No device access, calibration writes, or control acceptance. Camera image vertical
is a proxy: a good moving fit must also explain independent stationary poses.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np


def wrap(q):return (np.asarray(q)+math.pi)%(2*math.pi)-math.pi


def basis(q,order):
    q=np.atleast_1d(np.asarray(q,float))
    return np.column_stack([np.ones(len(q))]+[f(k*q) for k in range(1,order+1) for f in (np.sin,np.cos)])


def predict_camera_angle(q,coefficients):
    return float(wrap(float(q)+float(basis([q],(len(coefficients)-1)//2)[0]@coefficients)))


def slope(q,coefficients):
    return 1.+sum(k*coefficients[2*k-1]*math.cos(k*q)-k*coefficients[2*k]*math.sin(k*q)
                  for k in range(1,(len(coefficients)+1)//2))


def stats(error):
    x=np.degrees(wrap(error))
    if not len(x):return dict(n=0)
    return dict(n=len(x),rms_deg=float(np.sqrt(np.mean(x*x))),median_deg=float(np.median(x)),
                p95_abs_deg=float(np.percentile(abs(x),95)),max_abs_deg=float(max(abs(x))))


def arrays(rows):
    q=np.array([r['encoder_rad'] for r in rows],float);y=np.array([r['residual_rad'] for r in rows],float)
    if len(q)<100 or not np.isfinite(q).all() or not np.isfinite(y).all():raise ValueError('insufficient finite coverage')
    bins30=np.floor((wrap(q)+math.pi)/(math.pi/6)).astype(int).clip(0,11)
    counts=np.bincount(bins30,minlength=12);angles=np.sort(q%(2*math.pi))
    max_gap=float(max(np.diff(np.r_[angles,angles[0]+2*math.pi])))
    if (counts>=5).sum()<11 or max_gap>math.pi/4:raise ValueError('insufficient full-circle angular coverage')
    # Circular residuals are unwrapped about their circular mean, never by row order.
    center=math.atan2(float(np.sin(y).sum()),float(np.cos(y).sum()));y=wrap(y-center)+center
    bins=np.floor((wrap(q)+math.pi)/(math.pi/36)).astype(int).clip(0,71)
    return q,y,bins


def fit_coefficients(q,y,bins,order):
    counts=np.bincount(bins,minlength=72);weights=1/np.sqrt(counts[bins])
    matrix=basis(q,order)*weights[:,None]
    beta,_,rank,_=np.linalg.lstsq(matrix,y*weights,rcond=None)
    if rank!=matrix.shape[1]:raise ValueError('rank-deficient angle fit')
    return beta


def fit_candidate(training,opposite):
    q,y,bins=arrays(training);cv=[]
    for order in range(7):
        errors=[]
        for fold in range(6):
            held=bins%6==fold
            beta=fit_coefficients(q[~held],y[~held],bins[~held],order)
            errors.extend(wrap(y[held]-basis(q[held],order)@beta))
        cv.append(dict(order=order,**stats(errors)))
    best=min(r['rms_deg'] for r in cv)
    # Prefer a simpler numerical tie; no opposite-direction values select order.
    order=next(r['order'] for r in cv if r['rms_deg']<=best+1e-8)
    beta=fit_coefficients(q,y,bins,order)
    qv,yv,_=arrays(opposite)
    grid=np.linspace(-math.pi,math.pi,4097);derivative=np.array([slope(x,beta) for x in grid])
    return dict(order=order,coefficients=beta.tolist(),coefficient_units='radians',
        training_cross_validation=cv,training=stats(y-basis(q,order)@beta),
        opposite_direction=stats(yv-basis(qv,order)@beta),
        minimum_sampled_derivative=float(min(derivative)),maximum_sampled_derivative=float(max(derivative)),
        sampled_monotonic=bool(min(derivative)>0),camera_angle_at_saved_reference_deg=math.degrees(predict_camera_angle(0.,beta)),
        selection='First rotation direction only; six folds of interleaved 5-degree bins; bin-weighted fitting, frame-weighted held-fold CV; orders0..6. Opposite direction remains held out.',
        formula='camera_image_angle = wrap(q + beta0 + sum(beta[2*k-1]*sin(k*q) + beta[2*k]*cos(k*q))); q = wrap((raw-reference_counts)*2*pi/4096)')


def validate_stationary(candidate,holds,max_error_deg=.5):
    qualified=[h for h in holds if h['qualified']]
    errors=[float(wrap(h['camera_rad']-predict_camera_angle(h['encoder_rad'],candidate['coefficients']))) for h in qualified]
    result=stats(errors)
    return dict(**result,qualified_holds=len(qualified),passed=bool(qualified and result['max_abs_deg']<=max_error_deg),
                max_abs_error_deg=result.get('max_abs_deg'),limit_deg=max_error_deg,
                interpretation='Independent quiet-pose camera/encoder agreement; passing alone is not hardware acceptance.')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--moving-report',required=True,type=Path)
    p.add_argument('--pairs',required=True,type=Path)
    p.add_argument('--stationary-report',required=True,type=Path,action='append')
    p.add_argument('--output',required=True,type=Path);a=p.parse_args(argv)
    moving=json.loads(a.moving_report.read_text());direction=moving['training_direction']
    if not moving['entirely_disabled_healthy'] or direction not in (-1,1):raise ValueError('require healthy passive sweep with declared first direction')
    rows=[json.loads(line) for line in a.pairs.read_text().splitlines()]
    candidate=fit_candidate([r for r in rows if r['slow_motion_fit_eligible'] and r['direction']==direction],
                            [r for r in rows if r['slow_motion_fit_eligible'] and r['direction']==-direction])
    checks=[]
    for path in a.stationary_report:
        report=json.loads(path.read_text())
        if not report['entirely_disabled_healthy'] or report['reference_counts']!=moving['reference_counts']:
            raise ValueError('stationary check must be disabled with the same saved reference')
        holds=[dict(encoder_rad=h['native_encoder_angle_rad'],camera_rad=h['camera_image_angle_rad']['median'],qualified=h['stationary_comparison_qualified'])
               for h in report['holds'] if h['native_encoder_angle_rad'] is not None and h['camera_image_angle_rad'] is not None]
        checks.append(dict(source=str(path.resolve()),**validate_stationary(candidate,holds)))
    sources=[a.moving_report,a.pairs,*a.stationary_report,Path(__file__)]
    result=dict(schema='cartpole-encoder-periodic-candidate-v1',reference_counts=moving['reference_counts'],candidate=candidate,
                stationary_checks=checks,calibration_accepted=False,hardware_accepted=False,
                disposition='rejected_stationary_validation' if not all(c['passed'] for c in checks) else 'requires_independent_geometric_and_dynamic_validation',
                source_hashes=[dict(path=str(f.resolve()),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sources])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(a.output),order=candidate['order'],opposite_direction=candidate['opposite_direction'],stationary_checks=checks,disposition=result['disposition']),indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
