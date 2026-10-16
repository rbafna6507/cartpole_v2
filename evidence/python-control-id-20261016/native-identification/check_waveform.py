#!/usr/bin/env python3
"""Offline nominal waveform proposal. Never imports or accesses rig hardware."""
from pathlib import Path
import math,json
T=20.;R=2.
def waveform(t,A,fs):
    if t<0 or t>T:return (0.,)*4
    s=min(t,T-t)/R
    if s>=1:e,ed,edd,eddd=1.,0.,0.,0.
    else:
        sign=1 if t<=T/2 else -1
        e=10*s**3-15*s**4+6*s**5
        ed=sign*(30*s*s-60*s**3+30*s**4)/R
        edd=(60*s-180*s*s+120*s**3)/R**2
        eddd=sign*(60-360*s+360*s*s)/R**3
    g=[sum(A*(2*math.pi*f)**n*math.sin(2*math.pi*f*t+n*math.pi/2) for f in fs) for n in range(4)]
    return e*g[0],ed*g[0]+e*g[1],edd*g[0]+2*ed*g[1]+e*g[2],eddd*g[0]+3*edd*g[1]+3*ed*g[2]+e*g[3]

def check():
    result={}
    for name,A,fs in [('train',.0025,(.8,1.3,2.1)),('validation',.002,(.7,1.6,2.3))]:
        peaks=[0.]*4
        for i in range(200001):
            values=waveform(i/10000,A,fs)
            peaks=[max(a,abs(b)) for a,b in zip(peaks,values)]
        gs=[sum(A*(2*math.pi*f)**n for f in fs) for n in range(4)]
        # max |e'|=1.875/R, max |e''|=10*sqrt(3)/(3*R^2),
        # max |e'''|=60/R^3. Upper bound uses the next derivative
        # and nearest grid point (distance <=0.5*sample interval).
        max_edd=10*math.sqrt(3)/(3*R*R)
        bounds=[gs[0],.9375*gs[0]+gs[1],max_edd*gs[0]+1.875*gs[1]+gs[2],7.5*gs[0]+3*max_edd*gs[1]+3*.9375*gs[2]+gs[3]]
        certified=[peaks[k]+bounds[k+1]*.00005 for k in range(3)]
        assert max(abs(v) for v in waveform(0,A,fs))<1e-12
        assert max(abs(v) for v in waveform(T,A,fs))<1e-12
        assert certified[0]<.007 and certified[1]<.067 and certified[2]<.63
        for t in [.3,1.,1.7,3.33,19.,19.7]:
            h=1e-5;minus=waveform(t-h,A,fs);plus=waveform(t+h,A,fs);mid=waveform(t,A,fs)
            for j in range(3):assert abs((plus[j]-minus[j])/(2*h)-mid[j+1])<1e-6
        result[name]=dict(duration_s=T,ramp_s=R,amplitude_per_tone_m=A,frequencies_hz=fs,phases_rad=[0,0,0],envelope='quintic smoothstep 10s^3-15s^4+6s^5; two-second ramps',sample_interval_s=.0001,grid_abs_peaks=dict(zip(['x_m','v_m_s','a_m_s2','jerk_m_s3'],peaks)),analytic_global_bounds=dict(zip(['x_m','v_m_s','a_m_s2','jerk_m_s3'],bounds)),continuous_peak_upper_bound_from_grid=dict(zip(['x_m','v_m_s','a_m_s2'],certified)),endpoint_start=waveform(0,A,fs),endpoint_end=waveform(T,A,fs),hardware_activity=False)
    return result
if __name__=='__main__':
    result=check()
    (Path(__file__).resolve().parent/'waveform-proposal.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
