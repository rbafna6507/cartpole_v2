"""Recompute balance comparisons from preserved trajectories and source bindings."""
from hashlib import sha256
import json, math, os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/cartpole-confidence-mpl')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path('/Users/rbafna/projects/cartpole_v2')
OUT=Path(__file__).resolve().parent
TRAIN=ROOT/'runs/policy-confidence-20261021/balance'
CONFIRM=ROOT/'runs/policy-confidence-20261021/balance-confirmation'
def digest(path):return sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
def compact(episode,seconds):
    trace=episode['trajectory'];assert len(trace)==episode['steps']
    x=np.asarray([r['x'] for r in trace]);theta=np.asarray([r['theta'] for r in trace]);omega=np.asarray([r['omega'] for r in trace]);raw=np.asarray([r['raw'] for r in trace])
    balanced=(np.abs(x)<.12)&(np.abs(theta)<.15)&(np.abs(omega)<1.)
    full=episode['steps']==round(seconds*100) and episode['fault_reason'] is None
    tail_rms=float(np.sqrt(np.mean(x[-500:]**2)))
    jitter=float(np.sqrt(np.mean(np.diff(raw)**2))) if len(raw)>1 else 0.
    assert math.isclose(tail_rms,episode['tail_x_rms_m'],abs_tol=1e-12)
    assert math.isclose(jitter,episode['raw_action_delta_rms'],abs_tol=1e-12)
    assert math.isclose(float(balanced.sum())/(seconds*100),episode['balanced_fraction'],abs_tol=1e-12)
    assert bool(episode['hold_success'])==bool(full and np.all(balanced[-500:]) and len(trace)>=500)
    return dict(pose_seed=episode['seed'],complete=full,hold=bool(episode['hold_success']),full_balance=bool(full and np.all(balanced)),fault=episode['fault_reason'],decisions=len(trace),balanced_samples=int(balanced.sum()),balanced_fraction=episode['balanced_fraction'],tail_x_rms_m=tail_rms,max_abs_x_m=episode['max_abs_x_m'],raw_action_delta_rms_m_s2=jitter,tail_theta_rms_rad=episode['tail_theta_rms_rad'],first_one_second_capture_s=episode['first_one_second_capture_s'],longest_balance_dwell_s=episode['longest_balance_dwell_s'])
def aggregate(rows):
    return dict(episodes=len(rows),complete_episodes=sum(r['complete'] for r in rows),holds=sum(r['hold'] for r in rows),full_balance_episodes=sum(r['full_balance'] for r in rows),faults=sum(r['fault'] is not None for r in rows),decisions=sum(r['decisions'] for r in rows),balanced_samples=sum(r['balanced_samples'] for r in rows),mean_balanced_fraction=float(np.mean([r['balanced_fraction'] for r in rows])),minimum_balanced_fraction=min(r['balanced_fraction'] for r in rows),mean_tail_x_rms_m=float(np.mean([r['tail_x_rms_m'] for r in rows])),worst_max_abs_x_m=max(r['max_abs_x_m'] for r in rows),mean_raw_action_delta_rms_m_s2=float(np.mean([r['raw_action_delta_rms_m_s2'] for r in rows])),mean_tail_theta_rms_rad=float(np.mean([r['tail_theta_rms_rad'] for r in rows])))
def main():
    receipt=json.loads((CONFIRM/'result.json').read_text());assert receipt['completed']
    frozen=json.loads((CONFIRM/'protocol.json').read_text());assert frozen['initial_stage']['future_balance_confirmation_seeds']==list(range(94000,94008))
    bindings={};dev=[];long=[]
    for name in [f'{arm}-seed{seed}' for arm in ('scratch','teacher') for seed in (11,23,47)]:
        run=TRAIN/name;report=json.loads((run/'report.json').read_text());recipe=json.loads((run/'recipe.json').read_text())
        assert report['completed'] and digest(run/'recipe.json')==report['recipe_sha256']
        assert digest(run/'source.zip')==report['source_zip_sha256']
        assert all(report[k]==v for k,v in recipe.items())
        assert recipe['steps']==20480 and recipe['evaluation_seeds']==[93000,93001]
        for f in ('recipe.json','report.json','source.zip'):bindings[str((run/f).relative_to(ROOT))]=digest(run/f)
        for e in report['evaluations']:
            if e['steps'] not in (0,20480):continue
            cp=run/e['checkpoint'];assert digest(cp)==e['checkpoint_sha256'];bindings[str(cp.relative_to(ROOT))]=digest(cp)
            rows=[compact(row,10) for row in e['episodes']];assert len(rows)==2
            dev.append(dict(run=name,initialization=recipe['initialization'],optimizer_seed=recipe['optimizer_seed'],checkpoint_steps=e['steps'],aggregate=aggregate(rows),episodes=rows))
    for seed in (11,23,47):
        for step in (0,20480):
            name=f'teacher-seed{seed}-step{step:09d}';path=CONFIRM/name/'evaluation.json';r=json.loads(path.read_text())
            assert r['steps']==step and r['seeds']==list(range(94000,94008)) and r['seconds']==60 and r['starts']==['upright']
            source_report=json.loads((TRAIN/f'teacher-seed{seed}'/'report.json').read_text())
            selected=next(e for e in source_report['evaluations'] if e['steps']==step)
            assert r['checkpoint_sha256']==selected['checkpoint_sha256']
            bindings[str(path.relative_to(ROOT))]=digest(path)
            rows=[compact(row,60) for row in r['episodes']];assert len(rows)==8
            long.append(dict(run=f'teacher-seed{seed}',optimizer_seed=seed,checkpoint_steps=step,aggregate=aggregate(rows),episodes=rows,evaluation_path=str(path.relative_to(ROOT)),evaluation_sha256=digest(path)))
    pairs=[]
    for seed in (11,23,47):
        initial=next(r for r in long if r['optimizer_seed']==seed and r['checkpoint_steps']==0)
        final=next(r for r in long if r['optimizer_seed']==seed and r['checkpoint_steps']==20480)
        for a,b in zip(initial['episodes'],final['episodes']):
            assert a['pose_seed']==b['pose_seed']
            pairs.append(dict(optimizer_seed=seed,pose_seed=a['pose_seed'],initial_hold=a['hold'],final_hold=b['hold'],initial_full_balance=a['full_balance'],final_full_balance=b['full_balance'],tail_x_rms_delta_m=b['tail_x_rms_m']-a['tail_x_rms_m'],max_abs_x_delta_m=b['max_abs_x_m']-a['max_abs_x_m'],raw_action_delta_rms_delta_m_s2=b['raw_action_delta_rms_m_s2']-a['raw_action_delta_rms_m_s2'],balanced_fraction_delta=b['balanced_fraction']-a['balanced_fraction']))
    groups={}
    for stage in (0,20480):
        groups['initial' if stage==0 else 'final']=aggregate([e for r in long if r['checkpoint_steps']==stage for e in r['episodes']])
    development_groups={}
    for arm in ('scratch','teacher'):
        for stage in (0,20480):development_groups[f'{arm}-{stage}']=aggregate([e for r in dev if r['initialization']==arm and r['checkpoint_steps']==stage for e in r['episodes']])
    pair_summary=dict(pairs=len(pairs),tail_rms_improved=sum(p['tail_x_rms_delta_m']<0 for p in pairs),tail_rms_regressed=sum(p['tail_x_rms_delta_m']>0 for p in pairs),mean_tail_rms_delta_m=float(np.mean([p['tail_x_rms_delta_m'] for p in pairs])),mean_raw_jitter_delta_m_s2=float(np.mean([p['raw_action_delta_rms_delta_m_s2'] for p in pairs])))
    summary=dict(schema='cartpole-balance-confidence-analysis-v1',completed=True,hardware_accepted=False,deployable=False,simulation_only=True,protocol_sha256=digest(CONFIRM/'protocol.json'),analysis_script_sha256=digest(Path(__file__)),development=dev,development_groups=development_groups,confirmation=long,confirmation_groups=groups,paired_episodes=pairs,paired_summary=pair_summary,training_decisions=6*20480,development_decisions=sum(r['aggregate']['decisions'] for r in dev),confirmation_decisions=sum(r['aggregate']['decisions'] for r in long),units={'cart_distance':'m','raw_action_delta_rms':'m/s^2 per 100 Hz sample'},interpretation='Teacher initial and final actors are paired on eight fresh poses; three optimizer seeds share the same poses. Counts are repeated controller outcomes, not independent physical samples. No scratch confirmation was requested.',source_bindings=bindings)
    write(OUT/'summary.json',summary)
    colors=['#2563eb','#ea580c','#059669']
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for ax,metric,label,factor in [(axes[0,1],'mean_tail_x_rms_m','Mean final 5 s cart RMS (mm)',1000),(axes[1,0],'worst_max_abs_x_m','Worst displacement across 8 poses (mm)',1000),(axes[1,1],'mean_raw_action_delta_rms_m_s2','Mean raw command-change RMS (m/s² per sample)',1)]:
        for seed,color in zip((11,23,47),colors):
            points=[next(r['aggregate'][metric] for r in long if r['optimizer_seed']==seed and r['checkpoint_steps']==step)*factor for step in (0,20480)]
            ax.plot([0,1],points,'o-',color=color,lw=2,label=f'Optimizer seed {seed}')
        ax.set_xticks([0,1],['Initialized','After 20,480 decisions']);ax.set_xlim(-.12,1.12);ax.set_ylabel(label);ax.grid(axis='y',alpha=.2)
    axes[1,0].axhline(120,color='#64748b',linestyle='--',linewidth=1)
    axes[1,0].text(1.08,120,'120 mm hold bound',ha='right',va='bottom',fontsize=8,color='#64748b')
    axes[0,1].legend(frameon=False,fontsize=9)
    ax=axes[0,0];x=np.arange(2);width=.32
    ax.bar(x-width/2,[groups[k]['holds'] for k in ('initial','final')],width,label='Final 5 s hold',color='#2563eb')
    ax.bar(x+width/2,[groups[k]['full_balance_episodes'] for k in ('initial','final')],width,label='Entire 60 s balanced',color='#059669')
    for offset,metric in [(-width/2,'holds'),(width/2,'full_balance_episodes')]:
        for i,k in enumerate(('initial','final')):ax.text(i+offset,groups[k][metric]+.35,str(groups[k][metric]),ha='center',fontsize=10)
    ax.set_xticks(x,['Initialized','After 20,480 decisions']);ax.set_ylim(0,27);ax.set_ylabel('Successful controller / pose outcomes (of 24)');ax.legend(frameon=False,fontsize=9);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Paired 60-second balance confirmation • new encoder profile, bw10',fontsize=15)
    fig.supxlabel('Eight poses (94000–94007), reused for three optimizer seeds. Nominal simulation only; shared poses are not independent samples.',fontsize=9)
    fig.savefig(OUT/'comparison.png',dpi=180)
    plt.close(fig)
    write(OUT/'artifacts.json',{'summary_sha256':digest(OUT/'summary.json'),'comparison_png_sha256':digest(OUT/'comparison.png'),'analysis_script_sha256':digest(Path(__file__))})
    print(json.dumps({'development_groups':development_groups,'confirmation_groups':groups,'paired_summary':pair_summary},indent=2))
if __name__=='__main__':main()
