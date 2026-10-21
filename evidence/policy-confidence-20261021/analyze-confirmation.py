#!/usr/bin/env python3
"""Audit reserved-pose confirmation without changing the frozen candidate."""
import csv,json,math,os
from hashlib import sha256
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'runs/policy-confidence-20261021/joint-confirmation'
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def write(p,d):
    with Path(p).open('x') as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def mean(v):return float(np.mean(v)) if v and all(x is not None for x in v) else None

def audit_episode(mode,root,ep,seconds):
    path=root/ep['trace_path'];assert digest(path)==ep['trace_sha256']
    records=[json.loads(line) for line in path.open()];advanced=[r for r in records if r['physical_time_advanced']]
    states=np.asarray([[r['ground_truth_after'][k] for k in ('x','v','theta','omega')] for r in advanced],dtype=float)
    balanced=(abs(states[:,0])<.12)&(abs(states[:,2])<.15)&(abs(states[:,3])<1) if len(states) else np.array([],dtype=bool)
    expected=round(seconds*100);fault=ep.get('fault_reason') or ep.get('policy_fault_reason') or ep.get('simulator_fault_reason')
    full=fault is None and len(advanced)==expected
    assert len(advanced)<=expected
    assert bool(ep['hold_success'])==bool(full and len(balanced)>=500 and all(balanced[-500:]))
    assert ep['final_window_complete']==full
    if mode!='sdk':
        assert ep['steps']==len(records)
        assert math.isclose(float(balanced.sum())/expected,ep['balanced_fraction'],abs_tol=1e-12)
    else:assert ep['steps']==len(advanced)
    rawkey='sdk_raw_action_m_s2' if mode=='sdk' else 'requested_raw_action_m_s2'
    raw=[r[rawkey] for r in records if r[rawkey] is not None]
    tail_rms=float(np.sqrt(np.mean(states[-500:,0]**2))) if full else None
    if mode!='sdk' and full:assert math.isclose(tail_rms,ep['final_window_x_rms_m'],abs_tol=1e-12)
    longest=dwell=0;capture=None
    for i,yes in enumerate(balanced):
        dwell=dwell+1 if yes else 0;longest=max(longest,dwell)
        if capture is None and dwell>=100:capture=(i+1)/100
    assert math.isclose(longest/100,ep['longest_balance_dwell_s'],abs_tol=1e-8)
    assert (capture is None)==(ep['first_one_second_capture_s'] is None)
    if capture is not None:assert math.isclose(capture,ep['first_one_second_capture_s'],abs_tol=1e-8)
    maximum=max(abs(ep['initial_state'][0]),float(np.max(abs(states[:,0]))) if len(states) else 0.)
    assert math.isclose(maximum,ep['max_abs_x_m'],abs_tol=1e-12)
    row=dict(mode=mode,scenario=ep.get('scenario','nominal'),seed=ep['seed'],start=ep['start'],proposed=len(records),advanced=len(advanced),fault=fault,full_horizon=full,hold_success=ep['hold_success'],full_balance=bool(full and all(balanced)),balanced_fraction=float(balanced.sum())/expected,first_one_second_capture_s=capture,longest_balance_dwell_s=longest/100,final_window_x_rms_m=tail_rms,max_abs_x_m=maximum,raw_action_change_rms_m_s2=float(np.sqrt(np.mean(np.diff(raw)**2))) if len(raw)>1 else None,rapid_capture_and_30s_dwell=bool(capture is not None and capture<=5 and longest>=3000),trace_path=str(path.relative_to(ROOT)),trace_sha256=ep['trace_sha256'])
    return row,states,records[0].get('encoded_observation',records[0].get('actor_observation'))

def main():
    protocol=load(OUT/'confirmation-protocol.json');selection=load(OUT/'selection-frozen.json');selected=selection['selected']
    assert digest(OUT/'selection-frozen.json')==protocol['selection_sha256']
    assert digest(HERE/'joint-development.json')==protocol['selection_sha256']
    assert digest(HERE/'combined-selection-protocol.json')==protocol['selection_protocol_sha256']
    for name,pin in protocol['scripts'].items():assert digest(HERE/name)==pin
    for name,pin in protocol['selected_inputs'].items():assert digest(name)==pin
    rows=[];states={};observations={};reports={};bindings={};source_bindings={}
    for mode in ('nominal','sdk','stress'):
        root=OUT/mode;receipt=load(root/'receipt.json');binding=load(root/'binding.json');report=load(root/'evaluation/report.json');recipe=load(root/'evaluation/recipe.json')
        assert receipt['completed'] and report['completed']
        assert digest(root/'binding.json')==receipt['binding_sha256'] and digest(root/'evaluation/report.json')==receipt['report_sha256']
        assert digest(root/'evaluation/recipe.json')==report['recipe_sha256']
        assert binding['mode']==mode and binding['step']==selected['step'] and Path(binding['run']).resolve()==(ROOT/selected['run']).resolve()
        assert binding['checkpoint']==selected['checkpoint'] and binding['seconds']==protocol['confirmation'][mode+'_seconds']
        assert binding['seeds']==protocol['confirmation'][mode+'_seeds'] and recipe['seeds']==binding['seeds'] and recipe['seconds']==binding['seconds']
        assert recipe['checkpoint_sha256']==selected['checkpoint']['sha256']
        scenarios=protocol['confirmation']['stress_scenarios'] if mode=='stress' else ['nominal']
        assert {(e.get('scenario','nominal'),e['seed'],e['start']) for e in report['episodes']}=={(sc,s,st) for sc in scenarios for s in binding['seeds'] for st in ('hanging','upright')}
        assert len(report['episodes'])==len(scenarios)*len(binding['seeds'])*2
        command_receipt=load(OUT/(mode+'-command-receipt.json'));assert command_receipt['returncode']==0
        assert digest(OUT/(mode+'-command.json'))==command_receipt['command_sha256']
        if mode=='sdk':
            assert report['model_weights_sha256_before']==report['model_weights_sha256_after']
            assert digest(root/'evaluation/actor.json')==report['actor_file_sha256']==recipe['actor_file_sha256']
        for ep in report['episodes']:
            row,truth,obs=audit_episode(mode,root/'evaluation',ep,binding['seconds']);rows.append(row)
            if mode!='stress':states[(mode,ep['seed'],ep['start'])]=truth;observations[(mode,ep['seed'],ep['start'])]=(ep['initial_state'],obs)
        reports[mode]=report;bindings[mode]=binding
        for name in ('binding.json','receipt.json','evaluation/report.json','evaluation/recipe.json'):source_bindings[str((root/name).relative_to(ROOT))]=digest(root/name)
    groups=[]
    for mode in ('nominal','sdk','stress'):
        for scenario in (protocol['confirmation']['stress_scenarios'] if mode=='stress' else ['nominal']):
            for start in ('hanging','upright'):
                rr=[r for r in rows if r['mode']==mode and r['scenario']==scenario and r['start']==start]
                captures=[r['first_one_second_capture_s'] for r in rr]
                groups.append(dict(mode=mode,scenario=scenario,start=start,episodes=len(rr),faults=sum(r['fault'] is not None for r in rr),full_horizons=sum(r['full_horizon'] for r in rr),holds=sum(r['hold_success'] for r in rr),full_balance=sum(r['full_balance'] for r in rr),captures=sum(c is not None for c in captures),mean_capture_s_all_episodes=mean(captures),mean_capture_s_among_captured=mean([c for c in captures if c is not None]),rapid_capture_and_30s_dwell=sum(r['rapid_capture_and_30s_dwell'] for r in rr),mean_balanced_fraction=mean([r['balanced_fraction'] for r in rr]),mean_longest_balance_dwell_s=mean([r['longest_balance_dwell_s'] for r in rr]),mean_final_window_x_rms_m=mean([r['final_window_x_rms_m'] for r in rr]),tail_metrics_available=sum(r['final_window_x_rms_m'] is not None for r in rr),worst_max_abs_x_m=max(r['max_abs_x_m'] for r in rr),mean_raw_action_change_rms_m_s2=mean([r['raw_action_change_rms_m_s2'] for r in rr])))
    paired=[]
    for seed in protocol['confirmation']['nominal_seeds']:
        for start in ('hanging','upright'):
            aa=states[('nominal',seed,start)];bb=states[('sdk',seed,start)];n=min(len(aa),len(bb));delta=aa[:n]-bb[:n]
            match=observations[('nominal',seed,start)]==observations[('sdk',seed,start)]
            a=next(r for r in rows if (r['mode'],r['seed'],r['start'])==('nominal',seed,start));b=next(r for r in rows if (r['mode'],r['seed'],r['start'])==('sdk',seed,start))
            paired.append(dict(seed=seed,start=start,initial_state_and_encoded_observation_equal=match,nominal_hold=a['hold_success'],sdk_hold=b['hold_success'],nominal_capture_s=a['first_one_second_capture_s'],sdk_capture_s=b['first_one_second_capture_s'],nominal_tail_x_rms_m=a['final_window_x_rms_m'],sdk_tail_x_rms_m=b['final_window_x_rms_m'],compared_physical_states=n,max_abs_cart_trajectory_difference_m=float(np.max(abs(delta[:,0]))) if n else None,max_abs_wrapped_angle_trajectory_difference_rad=float(np.max(abs((delta[:,2]+np.pi)%(2*np.pi)-np.pi))) if n else None))
    parity={k:reports['sdk'][k] for k in ('emission_parity_pass','compared_actions','max_abs_raw_discrepancy_m_s2','raw_absolute_tolerance_m_s2','rejected_inputs','actor_file_sha256','actor_content_sha256','actor_runtime_sha256','inference_latency')}
    result=dict(schema='cartpole-joint-confirmation-analysis-v1',selected=selected,selection_sha256=protocol['selection_sha256'],confirmation_protocol_sha256=digest(OUT/'confirmation-protocol.json'),confirmation_outcomes_used_for_selection=False,hardware_accepted=False,groups=groups,episodes=rows,paired_nominal_sdk=paired,sdk_emission=parity,proposed_decisions=sum(r['proposed'] for r in rows),advanced_decisions=sum(r['advanced'] for r in rows),audited_episodes=len(rows),source_bindings=source_bindings,limitations=['One frozen candidate; no candidate replacement after reserved-pose outcomes.','Eight nominal common poses and two stress common poses; repeats across starts/scenarios and nominal/SDK are paired, not independent samples.','Development selection used two common poses across thirty checkpoints; selection may overfit.','Same-observation SDK emission agreement is distinct from trajectory and task success.','Simulation confirmation does not establish hardware success.'])
    write(HERE/'joint-confirmation-summary.json',result);write(OUT/'summary.json',result)
    for filename,data in [('joint-confirmation-episodes.csv',rows),('joint-confirmation-groups.csv',groups),('joint-confirmation-paired.csv',paired)]:
        with (HERE/filename).open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    os.environ.setdefault('MPLCONFIGDIR','/tmp/cartpole-confidence-mpl')
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(15,4.8),layout='constrained');colors={'nominal':'#0f766e','sdk':'#2563eb'}
    for mode,shift in [('nominal',-.12),('sdk',.12)]:
        h=[r for r in rows if r['mode']==mode and r['start']=='hanging'];u=[r for r in rows if r['mode']==mode and r['start']=='upright']
        axes[0].scatter([r['seed']-96000+shift for r in h],[r['first_one_second_capture_s'] if r['first_one_second_capture_s'] is not None else 62 for r in h],label=mode,color=colors[mode],s=38)
        axes[1].scatter([r['seed']-96000+shift for r in u],[1000*r['final_window_x_rms_m'] if r['final_window_x_rms_m'] is not None else float('nan') for r in u],label=mode,color=colors[mode],s=38)
    axes[0].axhline(5,color='#64748b',linestyle='--',lw=1);axes[0].set(title='Hanging: first one-second capture',xlabel='Pose seed − 96000',ylabel='Seconds (62 = no capture)',ylim=(-1,65));axes[0].legend()
    axes[1].set(title='Upright: final five-second cart RMS',xlabel='Pose seed − 96000',ylabel='Millimeters');axes[1].legend()
    labels=protocol['confirmation']['stress_scenarios'];x=np.arange(len(labels))
    for start,shift,color in [('hanging',-.17,'#b45309'),('upright',.17,'#0f766e')]:
        gg=[next(g for g in groups if g['mode']=='stress' and g['scenario']==sc and g['start']==start) for sc in labels]
        axes[2].bar(x+shift,[g['holds']/g['episodes'] for g in gg],width=.32,label=start,color=color)
    axes[2].set(title='Stress: final five-second holds',ylabel='Fraction of two common poses',xticks=x,xticklabels=['Nominal','Bias −','Combined −','Bias +','Combined +'],ylim=(0,1.08));axes[2].tick_params(axis='x',rotation=25);axes[2].legend()
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle(f"Frozen {selected['group']} seed {selected['optimizer_seed']} / step {selected['step']:,}: 60-second reserved-pose confirmation",fontsize=13)
    fig.supxlabel('Nominal and SDK reuse eight paired poses; stress reuses two other poses. Simulation only. No holdout-based reselection.',fontsize=9)
    fig.savefig(HERE/'joint-confirmation.png',dpi=180);plt.close(fig)
    print(json.dumps(dict(selected=selected,groups=groups,sdk_emission=parity,audited_episodes=len(rows)),indent=2))
if __name__=='__main__':main()
