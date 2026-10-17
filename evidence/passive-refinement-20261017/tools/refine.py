#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3"]
# ///
"""Training-only passive refinement, then frozen regression. No hardware/export."""
import argparse, datetime, gzip, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
import scipy
from scipy.optimize import least_squares, lsq_linear
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
OLD = ROOT/'evidence/system-id-model-review-20261017'
LATER = ROOT/'evidence/passive-batches8-9-20261017'
sys.path[:0] = [str(ROOT/'src'), str(OLD/'tools')]
from cartpole_sdk.identification import workflow, passive, release_review
from dynamics import ode_solution, initial_state, metrics
from trajectory import trajectory_sensitivity
TRAIN = ['training6','development6','training8','training9']
VALID = ['validation8','validation9']
BASELINE = [60.806177009128575,0.006891975341585199,6.898766153634008,1.6268943123178277]
CFG = dict(passive.DEFAULT_GATES,window_s=.35)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(p,v):
    p=Path(p)
    if p.exists(): raise FileExistsError(p)
    data=(json.dumps(v,indent=2,allow_nan=False)+'\n').encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix=='.gz' else data)
def read(p):
    p=Path(p); data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)
def hashes():
    paths=[HERE/'METHOD.md',Path(__file__),OLD/'tools/dynamics.py',OLD/'tools/trajectory.py',ROOT/'src/cartpole_sdk/identification/passive.py',ROOT/'src/cartpole_sdk/identification/workflow.py',ROOT/'src/cartpole_sdk/identification/release_review.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}
def source_paths(label):
    if label in ('training6','development6'):
        role='training' if label=='training6' else 'validation'
        ann=OLD/f'batch6/{role}-annotations.json'
        paths=list((ROOT/f'runs/passive-batch6-original/passive-{role}-6').glob('rig-*.jsonl'))
        archive=OLD/f'batch6/{role}-original.tar.xz'
    else:
        role=label[:-1];batch=label[-1]
        ann=LATER/label/'annotations.json'
        paths=list((ROOT/f'runs/passive-batches8-9-{label}-original/passive-{role}-{batch}').glob('rig-*.jsonl'))
        archive=LATER/label/'original.tar.xz'
    # workflow supports archive::member; one raw recording per preserved archive.
    if paths: source=str(paths[0])
    else:
        import tarfile
        with tarfile.open(archive) as tf: members=[n for n in tf.getnames() if n.endswith('.jsonl')]
        if len(members)!=1: raise ValueError('expected one raw JSONL')
        source=str(archive)+'::'+members[0]
    return source,ann,archive

def load(labels):
    records=[]
    for label in labels:
        source,ann,archive=source_paths(label)
        eps,identity=workflow.passive_episodes(source,ann)
        parts=passive.segments(eps,CFG)
        assert len(parts)==len(eps), 'split/skipped segments require explicit treatment'
        quality=release_review.analyze_releases(source,ann)
        print('loaded',label,len(parts),identity['sha256'],flush=True)
        records.append(dict(label=label,identity=identity,parts=parts,quality=quality,annotations=str(ann.relative_to(ROOT)),annotations_sha256=sha(ann),archive=str(archive.relative_to(ROOT)),archive_sha256=sha(archive)))
    assert len({r['identity']['sha256'] for r in records})==len(records)
    return records

def identity(r):
    return {k:v for k,v in r.items() if k!='parts'}
def coefficients(c):
    return dict(effective_length_m=9.81/math.hypot(c[0],c[2]),viscous_per_s=float(c[1]),coulomb_rad_per_s2=float(c[3]),local_angle_offset_rad=math.atan2(-c[2],c[0]))

def robust_initial(t,q,i,c,duration):
    lo=max(0,int(np.searchsorted(t,t[i]-duration-1e-9)))
    ts=t[lo:i+1];qs=q[lo:i+1]
    w=np.polyfit(ts-ts[0],qs,2)[-2]
    fit=least_squares(lambda z:ode_solution(ts,z,c)[0]-qs,[qs[0],w],loss='soft_l1',f_scale=.02,xtol=1e-7,ftol=1e-7,gtol=1e-7,max_nfev=30)
    if not fit.success: raise ValueError('causal initializer failed: '+fit.message)
    return ode_solution(ts,fit.x,c)[:,-1]
def state(t,q,i,c,method,duration):
    if method=='frozen_rawq': return initial_state(t,q,i,c,'history_rawq:'+str(duration))
    if method=='robust_history': return robust_initial(t,q,i,c,duration)
    raise ValueError(method)
def wrapped(e): return np.arctan2(np.sin(e),np.cos(e))
def score_record(r,c,method):
    rows=[]; pooled={'short':[],'.25':[],'.5':[]}
    for t,q,ident in r['parts']:
        i=max(10,int(np.searchsorted(t,t[0]+.1)));short=[];windows=[]
        while i+8<len(t):
            end=int(np.searchsorted(t,t[i]+.5,side='right'))
            if t[end-1]-t[i]<.45: break
            z=state(t,q,i,c,method,.2)
            pred=ode_solution(t[i:end],z,c)[0]
            err=wrapped(pred[1:]-q[i+1:end]);short.extend(err)
            windows.append(dict(index=i,end=end,history_end_s=float(t[i]),initial_state=z.tolist()))
            i=end
        row=dict(episode_id=ident[1],short=metrics(short),short_errors_rad=np.asarray(short).tolist(),short_windows=windows,continuous={})
        row['short_numeric_pass']=math.radians(row['short']['rms_deg'])<=.08 and math.radians(row['short']['p95_deg'])<=.15
        row['short_coverage_pass']=len(windows)>=3
        pooled['short'].extend(short)
        for duration,key in [(.25,'.25'),(.5,'.5')]:
            i=int(np.searchsorted(t,t[0]+duration));z=state(t,q,i,c,method,duration)
            pred=ode_solution(t[i:],z,c)[0];err=wrapped(pred[1:]-q[i+1:]);pooled[key].extend(err)
            row['continuous'][key]=dict(metrics=metrics(err),initial_state=z.tolist(),initialization_samples=i+1,t_s=t[i:].tolist(),observed_rad=q[i:].tolist(),predicted_rad=pred.tolist(),errors_rad=err.tolist())
        rows.append(row)
    return dict(label=r['label'],metrics={k:metrics(v) for k,v in pooled.items()},releases=rows,skipped=[])
def evaluate(records,c,method):
    rows=[]
    for r in records:
        start=time.time();x=score_record(r,c,method);rows.append(x)
        print('score',r['label'],method, {k:round(v['rms_deg'],4) for k,v in x['metrics'].items()},'seconds',round(time.time()-start,1),flush=True)
    return rows

def weak_fit(parts,robust=False):
    x,y=passive.matrix(parts,CFG,'viscous_coulomb')
    fit=lsq_linear(x,y,bounds=([20,0,-40,0],[150,5,40,20]),tol=1e-12)
    scale=.1*float(np.std(y))
    if robust: fit=least_squares(lambda c:x@c-y,fit.x,jac=lambda c:x,loss='soft_l1',f_scale=scale,bounds=([20,0,-40,0],[150,5,40,20]),xtol=1e-12,ftol=1e-12,gtol=1e-12,max_nfev=1000)
    if not fit.success: raise ValueError(fit.message)
    return fit.x,dict(success=bool(fit.success),weak_windows=len(y),rank=int(np.linalg.matrix_rank(x)),condition=float(np.linalg.cond(x/np.linalg.norm(x,axis=0))),nrmse=passive.nrmse(x,y,fit.x),loss='soft_l1' if robust else 'linear',f_scale=scale if robust else None)

def trajectory_fit(parts,base):
    slices=[];x0=list(base);lower=[20,0,-40,0];upper=[150,5,40,20];offset=4;weights=[]
    for t,q,ident in parts:
        ix=np.r_[np.arange(0,len(t)-1,5),len(t)-1];ts=t[ix];qs=q[ix]
        z=[q[0],np.polyfit(t[:25]-t[0],q[:25],2)[-2]]
        x0.extend(z);lower.extend([q[0]-.35,-30]);upper.extend([q[0]+.35,30]);slices.append((ts,qs,offset));offset+=2;weights.extend([1/len(ts)]*len(ts))
    weights=np.array(weights);cache={};calls=0
    def evaluate(x):
        nonlocal calls
        if 'x' in cache and np.array_equal(cache['x'],x): return
        rr=[];jj=[]
        for t,q,offset in slices:
            pred,deriv=trajectory_sensitivity(t,x[offset:offset+2],x[:4]);rr.extend(pred-q)
            jac=np.zeros((len(t),len(x)));jac[:,:4]=deriv[:,:4];jac[:,offset:offset+2]=deriv[:,4:];jj.append(jac)
        cache.update(x=x.copy(),r=np.asarray(rr),j=np.concatenate(jj));calls+=1
        if calls%3==1: print('trajectory evaluation',calls,'rms',float(np.rad2deg(np.sqrt(np.mean(cache['r']**2)))),'coefficients',x[:4].tolist(),flush=True)
    def fun(x): evaluate(x);return cache['r']
    def jac(x): evaluate(x);return cache['j']
    def loss(z):
        v=np.sqrt(1+z)
        return np.vstack([2*(v-1),1/v,-.5/v**3])*weights[None,:]
    result=least_squares(fun,x0,jac=jac,bounds=(lower,upper),loss=loss,f_scale=.03,x_scale='jac',max_nfev=70,ftol=2e-7,xtol=2e-7,gtol=2e-7)
    return result.x[:4],dict(success=bool(result.success),message=result.message,nfev=result.nfev,cost=float(result.cost),optimality=float(result.optimality),training_nuisance_initial_states=result.x[4:].reshape(-1,2).tolist(),loss='equal-release weighted soft_l1',f_scale_rad=.03)

def signature_check():
    t=np.linspace(0,.7,72);z=np.array([3.45,-1.7]);c=np.array(BASELINE);q,j=trajectory_sensitivity(t,z,c);errors=[]
    for k in range(6):
        h=1e-4;cp=c.copy();cm=c.copy();zp=z.copy();zm=z.copy()
        if k<4: cp[k]+=h;cm[k]-=h
        else: zp[k-4]+=h;zm[k-4]-=h
        plus=trajectory_sensitivity(t,zp,cp)[0];minus=trajectory_sensitivity(t,zm,cm)[0]
        errors.append(float(np.max(abs((plus-minus)/(2*h)-j[:,k]))))
    if max(errors)>2e-3: raise AssertionError(errors)
    return dict(finite_difference_max_abs_errors=errors,passed=True)
def mean_metric(rows,key): return float(np.mean([r['metrics'][key]['rms_deg'] for r in rows]))
def selection(models):
    baseline=models[0];base=baseline['records'];out=[]
    for m in models:
        rows=m['records'];primary=mean_metric(rows,'.5');checks={
            'primary_improves_5pct':primary<=.95*mean_metric(base,'.5'),
            'short_mean_no_more_2pct_worse':mean_metric(rows,'short')<=1.02*mean_metric(base,'short'),
            'quarter_history_mean_no_more_5pct_worse':mean_metric(rows,'.25')<=1.05*mean_metric(base,'.25'),
            'every_recording_primary_within_10pct':all(r['metrics']['.5']['rms_deg']<=1.1*b['metrics']['.5']['rms_deg'] for r,b in zip(rows,base)),
            'preserves_baseline_short_gates':all((not be['short_numeric_pass'] or e['short_numeric_pass']) and (not be['short_coverage_pass'] or e['short_coverage_pass']) for r,b in zip(rows,base) for e,be in zip(r['releases'],b['releases']))}
        out.append(dict(name=m['name'],eligible=all(checks.values()),checks=checks,equal_recording_rms={k:mean_metric(rows,k) for k in ['short','.25','.5']}))
    eligible=[x for x in out if x['eligible']]
    chosen=min(eligible,key=lambda x:x['equal_recording_rms']['.5'])['name'] if eligible else baseline['name']
    return chosen,out

def train(output,reuse_fits=None):
    output.mkdir(parents=True,exist_ok=True)
    if (output/'candidate-freeze.json').exists() or (output/'training.json.gz').exists(): raise FileExistsError(output)
    preflight=signature_check();records=load(TRAIN);parts=[p for r in records for p in r['parts']]
    if reuse_fits:
        cached=read(reuse_fits)
        assert cached['source_hashes']=={r['label']:r['identity']['sha256'] for r in records}
        assert cached['method_hashes'][str((HERE/'METHOD.md').relative_to(ROOT))]==sha(HERE/'METHOD.md')
        fits=cached['fits']
        print('reusing completed fits with unchanged data and pre-fit method',sha(reuse_fits),flush=True)
    else:
        fits={'baseline':dict(coefficients=BASELINE,fit=dict(frozen=True))}
        for name,robust in [('pooled_weak',False),('robust_weak',True)]:
            c,info=weak_fit(parts,robust);fits[name]=dict(coefficients=c.tolist(),fit=info);print(name,fits[name],flush=True)
        c,info=trajectory_fit(parts,np.array(fits['robust_weak']['coefficients']));fits['robust_trajectory']=dict(coefficients=c.tolist(),fit=info)
        write(output/'fits.json',dict(created_at_utc=now(),fits=fits,preflight=preflight,source_hashes={r['label']:r['identity']['sha256'] for r in records},method_hashes=hashes()))
    models=[]
    for name,item in fits.items():
        if not item['fit'].get('success',True): continue
        for method in ['frozen_rawq','robust_history']:
            print('evaluating',name,method,flush=True)
            rows=evaluate(records,item['coefficients'],method)
            models.append(dict(name=name+'/'+method,coefficients=item['coefficients'],initializer=method,parameters=coefficients(item['coefficients']),records=rows))
            write(output/f"training-{name}-{method}.json.gz",models[-1])
    stable=[]
    for r in records:
        c,info=weak_fit([p for other in records if other is not r for p in other['parts']],True)
        stable.append(dict(omitted_recording=r['label'],coefficients=c.tolist(),parameters=coefficients(c),fit=info))
    selected,table=selection(models);chosen=next(m for m in models if m['name']==selected)
    training=dict(schema='passive-training-refinement-v1',created_at_utc=now(),source_identities=[identity(r) for r in records],fits=fits,models=models,selection=table,selected=selected,weak_leave_one_recording_out=stable,preflight=preflight,method_hashes=hashes(),reused_fit_report_sha256=sha(reuse_fits) if reuse_fits else None)
    write(output/'training.json.gz',training)
    freeze=dict(schema='passive-refinement-freeze-v1',created_at_utc=now(),scope='DEVELOPMENT_ONLY; validation8/9 are previously inspected regression holdouts',coefficients=chosen['coefficients'],initializer=chosen['initializer'],candidate_name=selected,parameters=chosen['parameters'],baseline=dict(coefficients=BASELINE,initializer='frozen_rawq',freeze_path=str((OLD/'candidate-freeze-latest6.json').relative_to(ROOT)),freeze_sha256=sha(OLD/'candidate-freeze-latest6.json')),selection=table,development_source_sha256=[r['identity']['sha256'] for r in records],training_sources=[{k:v for k,v in identity(r).items() if k not in ['quality','identity']}|dict(raw_sha256=r['identity']['sha256']) for r in records],training_report_sha256=sha(output/'training.json.gz'),method_hashes=hashes(),histories_s=[.25,.5],primary_history_s=.5,friction_law='-c*tanh(omega/0.05)',production_export_allowed=False,accepted=False)
    write(output/'candidate-freeze.json',freeze);write(output/'training-selection.json',dict(selected=selected,models=table,freeze_sha256=sha(output/'candidate-freeze.json')))
    print('FROZEN',selected,chosen['parameters'],flush=True)

def regression(output,freeze_path):
    if (output/'regression.json.gz').exists(): raise FileExistsError(output/'regression.json.gz')
    freeze=read(freeze_path)
    for path,digest in freeze['method_hashes'].items():
        if sha(ROOT/path)!=digest: raise ValueError('frozen method changed: '+path)
    records=load(VALID)
    assert not {r['identity']['sha256'] for r in records}&set(freeze['development_source_sha256'])
    rows=[]
    for name,c,method in [('baseline',BASELINE,'frozen_rawq'),('candidate',freeze['coefficients'],freeze['initializer'])]:
        rows.append(dict(name=name,coefficients=c,initializer=method,records=evaluate(records,c,method)))
    result=dict(schema='passive-frozen-regression-v1',created_at_utc=now(),freeze_sha256=sha(freeze_path),source_identities=[identity(r) for r in records],models=rows,previously_inspected=True,new_blind_validation=False,accepted=False,exported=False)
    write(output/'regression.json.gz',result)
    print('REGRESSION SAVED',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['train','regression']);p.add_argument('--output',type=Path,default=HERE);p.add_argument('--freeze',type=Path);p.add_argument('--reuse-fits',type=Path,help='Resume completed training fits after a reporting-only correction; source/method hashes must match');a=p.parse_args()
    if a.stage=='train':train(a.output,a.reuse_fits)
    else:regression(a.output,a.freeze or a.output/'candidate-freeze.json')
if __name__=='__main__':main()
