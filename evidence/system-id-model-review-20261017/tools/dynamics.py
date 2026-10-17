"""Offline developmental diagnostics; never promotes or exports a model."""
import argparse, json, math, hashlib
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
from cartpole_sdk.identification import workflow, passive


def ode_solution(t, initial, c):
    a,g,b=c[:3]; fc=c[3] if len(c)>3 else 0.; quad=c[4] if len(c)>4 else 0.
    def rhs(t,s):
        q,w=s
        return [w,a*np.sin(q)+b*np.cos(q)-g*w-fc*np.tanh(w/.05)-quad*w*abs(w)]
    sol=solve_ivp(rhs,(float(t[0]),float(t[-1])),initial,t_eval=t,rtol=2e-8,atol=1e-10,max_step=.02,method='DOP853')
    if not sol.success or sol.y.shape[1]!=len(t):raise ValueError(sol.message)
    return sol.y


def initial_state(t,q,i,c,method):
    if method=='original':return np.array([q[i],np.polyfit(t[i-10:i+1]-t[i],q[i-10:i+1],2)[-2]])
    kind,duration=method.split(':');duration=float(duration)
    lo=max(0,np.searchsorted(t,t[i]-duration-1e-9));ts=t[lo:i+1];qs=q[lo:i+1]
    if kind in ('poly2','poly3'):
        p=np.polyfit(ts-ts[-1],qs,int(kind[-1]));return np.array([qs[-1],p[-2]])
    w=np.polyfit(ts-ts[0],qs,2)[-2]
    def residual(z):return ode_solution(ts,z,c)[0]-qs
    fit=least_squares(residual,[qs[0],w],xtol=1e-7,ftol=1e-7,gtol=1e-7,max_nfev=15)
    state=ode_solution(ts,fit.x,c)[:,-1]
    if kind=='history_rawq':state[0]=qs[-1]
    return state


def metrics(e):
    e=np.array(e);return dict(rms_deg=float(np.rad2deg(np.sqrt(np.mean(e*e)))),p95_deg=float(np.rad2deg(np.quantile(abs(e),.95))),samples=len(e))


def score(parts,c,method,trace=False):
    errors=[];continuous_errors=[];per=[];skipped=[]
    for t,q,identity in parts:
        i=max(10,int(np.searchsorted(t,t[0]+.1)));start=i;ee=[];states=[]
        if i+8>=len(t):
            skipped.append(dict(identity=identity,duration_s=float(t[-1]-t[0]),samples=len(t),reason='segment too short to initialize and forecast'));continue
        while i+8<len(t):
            end=int(np.searchsorted(t,t[i]+.5,side='right'))
            if t[end-1]-t[i]<.45:break
            state=initial_state(t,q,i,c,method);pred=ode_solution(t[i:end],state,c)[0]
            err=np.arctan2(np.sin(pred[1:]-q[i+1:end]),np.cos(pred[1:]-q[i+1:end]));ee.extend(err)
            states.append(dict(t_s=float(t[i]),q_rad=float(state[0]),w_rad_s=float(state[1])))
            i=end
        state=initial_state(t,q,start,c,method);pred=ode_solution(t[start:],state,c)[0]
        ce=np.arctan2(np.sin(pred[1:]-q[start+1:]),np.cos(pred[1:]-q[start+1:]));continuous_errors.extend(ce);errors.extend(ee)
        row=dict(episode_id=identity[1],short=metrics(ee) if ee else None,continuous=metrics(ce),initial_states=states)
        if trace:row['trace']=dict(t=t[start:].tolist(),measured=q[start:].tolist(),predicted=pred.tolist())
        per.append(row)
    return dict(short=metrics(errors),continuous=metrics(continuous_errors),episodes=per,skipped_segments=skipped)


