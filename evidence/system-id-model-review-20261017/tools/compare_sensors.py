#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3"]
# ///
"""Fit relative camera timing and shape on training only; test unchanged on development data.
No timestamps or calibration files are rewritten. Geometry is not absolute truth.
"""
import argparse,json,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from cartpole_sdk.identification import release_review as rr,workflow


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for role in ['training','validation']:
        p.add_argument('--'+role,type=Path,required=True);p.add_argument('--'+role+'-annotations',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    data={};ids={}
    for role in ['training','validation']:
        report,(t,q,frames)=rr._analyze(str(getattr(a,role)),getattr(a,role+'_annotations'));ids[role]=report['source_identity'];annotations=workflow.read_json(getattr(a,role+'_annotations'))
        valid=[f for f in frames if f['valid'] and f['t_s'] is not None];ct=np.array([f['t_s'] for f in valid]);cq=np.array([f['angle_rad'] for f in valid]);mask=np.zeros(len(ct),bool)
        for ep in annotations['episodes']:
            lo,hi=ep['board_relative_s'];mask|=(ct>=lo+.07)&(ct<=hi-.07)
        data[role]=(t,q,ct[mask],cq[mask])
    workflow._independent(ids['training'],ids['validation'])
    def basis(q):return np.array([np.sin(q),1-np.cos(q),np.sin(2*q),1-np.cos(2*q)]).T
    def residual(x,role):
        t,q,ct,cq=data[role];qe=np.interp(ct-x[0],t,q)
        return qe+(basis(qe)@x[1:] if len(x)>1 else 0)-cq
    rows=[]
    for kind in ['unmodified','delay_only','delay_and_static_mapping']:
        n=5 if kind=='delay_and_static_mapping' else 1
        x=np.zeros(n)
        if kind!='unmodified':x=least_squares(lambda x:residual(x,'training'),x,bounds=([-.06]+[-.3]*(n-1),[.06]+[.3]*(n-1)),max_nfev=100,ftol=1e-10,xtol=1e-10,gtol=1e-10).x
        row=dict(kind=kind,fitted_parameters=x.tolist(),score={})
        for role in data:
            r=residual(x,role);row['score'][role]=dict(rms_deg=float(np.rad2deg(np.sqrt(np.mean(r*r)))),p95_deg=float(np.rad2deg(np.quantile(abs(r),.95))),samples=len(r))
        rows.append(row)
    report=dict(scope='Development diagnostic; no automatic calibration or export',accepted=False,source_identities=ids,results=rows,method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_timestamps_changed=False,
        interpretation='Positive delay means a camera frame corresponds to an earlier encoder reading. Relative delay combines unknown capture, exposure, tracking and receipt latencies; it is not certified physical exposure delay.',
        limitations=['Camera apparent projected angles are not absolute physical-angle truth.','Both recordings are development evidence after this comparison.','Shape mapping is local to observed angles and is not an accepted encoder calibration.','Every model uses the same samples; 70ms edge margin protects against the fixed +/-60ms delay search.'])
    workflow.write_json(a.output,report);print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
