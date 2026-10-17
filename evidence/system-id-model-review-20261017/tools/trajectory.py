"""Training-only full-decay trajectory fit, held development recording replay.
Uses analytic ODE sensitivities; initial poses/velocities are training nuisances.
"""
import argparse,json,math
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
from cartpole_sdk.identification import workflow,passive
from dynamics import score


def trajectory_sensitivity(t,z,c):
    n=len(c);a,g,b=c[:3];fc=c[3] if n>3 else 0.;drag=c[4] if n>4 else 0.
    sens=np.zeros((2,n+2));sens[0,n]=1;sens[1,n+1]=1
    def rhs(t,s):
        q,w=s[:2];v=s[2:].reshape(2,n+2);tanh=np.tanh(w/.05)
        force=a*np.sin(q)+b*np.cos(q)-g*w-fc*tanh-drag*w*abs(w)
        jac=np.array([[0.,1.],[a*np.cos(q)-b*np.sin(q),-g-fc*(1-tanh*tanh)/.05-2*drag*abs(w)]])
        dv=jac@v;dv[1,:n]+=np.array([np.sin(q),-w,np.cos(q),-tanh,-w*abs(w)])[:n]
        return np.r_[w,force,dv.ravel()]
    sol=solve_ivp(rhs,(t[0],t[-1]),np.r_[z,sens.ravel()],t_eval=t,rtol=2e-7,atol=1e-9,max_step=.03,method='DOP853')
    if not sol.success:raise ValueError(sol.message)
    return sol.y[0],sol.y[2:].T.reshape(-1,2,n+2)[:,0,:]


def fit_trajectory(parts,base,model):
    count={'viscous':3,'coulomb':4,'quadratic':5}[model];c=np.r_[base,np.zeros(count-3)]
    # Quadratic tests retain nonnegative Coulomb and quadratic drag.
    slices=[];offset=count;initial=list(c);lower=[20,0,-40]+[0]*(count-3);upper=[150,5,40]+[20,2][:count-3]
    for t,q,identity in parts:
        ix=np.r_[np.arange(0,len(t)-1,5),len(t)-1];ts=t[ix];qs=q[ix]
        z=[q[0],np.polyfit(t[:25]-t[0],q[:25],2)[-2]]
        initial.extend(z);lower.extend([q[0]-.35,-30]);upper.extend([q[0]+.35,30]);slices.append((ts,qs,offset));offset+=2
    cached=None;rr=None;jj=None;calls=0
    def evaluate(x):
        nonlocal cached,rr,jj,calls
        if cached is not None and np.array_equal(cached,x):return
        r=[];jac=[]
        for t,q,offset in slices:
            pred,deriv=trajectory_sensitivity(t,x[offset:offset+2],x[:count]);weight=1/np.sqrt(len(t));r.extend((pred-q)*weight)
            j=np.zeros((len(t),len(x)));j[:,:count]=deriv[:,:count];j[:,offset:offset+2]=deriv[:,count:];jac.append(j*weight)
        rr=np.array(r);jj=np.concatenate(jac);cached=x.copy();calls+=1
    def fun(x):evaluate(x);return rr
    def jac(x):evaluate(x);return jj
    result=least_squares(fun,initial,jac=jac,bounds=(lower,upper),x_scale='jac',max_nfev=70,ftol=2e-8,xtol=2e-8,gtol=2e-8)
    return result.x[:count],dict(success=bool(result.success),message=result.message,nfev=result.nfev,cost=float(result.cost),optimality=float(result.optimality),training_initial_states=result.x[count:].reshape(-1,2).tolist())


