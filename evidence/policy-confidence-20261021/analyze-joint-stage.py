#!/usr/bin/env python3
"""Audit ten frozen development runs and select once before confirmation."""
import argparse,csv,json,math,os,posixpath,zipfile
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent

def hashed(path):return sha256(Path(path).read_bytes()).hexdigest()
def write_new(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
def rank_episodes(episodes):
    up=[e for e in episodes if e['start']=='upright'];hang=[e for e in episodes if e['start']=='hanging']
    eligible=bool(len(up)==2 and len(hang)==2 and all(e['balanced_fraction']>=1.-1e-12 for e in up) and all(e['fault_reason'] is None for e in episodes))
    captured=[e['first_one_second_capture_s'] for e in hang if e['hold_success']]
    assert all(v is not None and math.isfinite(v) for v in captured)
    rank=[sum(e['hold_success'] for e in hang),-float(np.mean(captured)) if captured else -1e9,float(np.mean([e['longest_balance_dwell_s'] for e in hang]))]
    return eligible,rank

def self_check():
    def episodes(holds,capture,up_fraction=1.):
        return [dict(start='upright',balanced_fraction=up_fraction,fault_reason=None,hold_success=True,first_one_second_capture_s=1.,longest_balance_dwell_s=25.) for _ in range(2)]+[dict(start='hanging',balanced_fraction=.5,fault_reason=None,hold_success=i<holds,first_one_second_capture_s=capture if i<holds else None,longest_balance_dwell_s=10. if i<holds else 0.) for i in range(2)]
    initial=rank_episodes(episodes(1,8.));regressed=rank_episodes(episodes(2,4.,.999));faster=rank_episodes(episodes(1,5.));more=rank_episodes(episodes(2,20.))
    assert initial[0] and not regressed[0] and faster[1]>initial[1] and more[1]>faster[1]
    tied=[dict(name='first',rank=initial[1]),dict(name='second',rank=initial[1])]
    assert max(tied,key=lambda c:tuple(c['rank']))['name']=='first'
    print('Selection checks passed: upright regression excluded; holds precede speed; speed breaks equal holds; initial eligible; stable ties.')

def trace_audit(path,episode,seconds):
    assert hashed(path)==episode['trace_sha256']
    proposed=advanced=balanced=0;last=[];maximum=0.
    with path.open() as stream:
        for line in stream:
            row=json.loads(line);proposed+=1
            if not row['physical_time_advanced']:continue
            advanced+=1;truth=row['ground_truth_after'];maximum=max(maximum,abs(truth['x']))
            yes=abs(truth['theta'])<.15 and abs(truth['omega'])<1 and abs(truth['x'])<.12
            balanced+=yes
            if row['elapsed_since_reset_s']>seconds-5:last.append(yes)
    assert proposed==episode['steps']
    assert math.isclose(balanced/(seconds*100),episode['balanced_fraction'],abs_tol=1e-12)
    complete=episode['fault_reason'] is None and advanced==round(seconds*100)
    assert bool(episode['hold_success'])==bool(complete and len(last)>=500 and all(last))
    assert episode['max_abs_x_m']+1e-12>=maximum
    return dict(proposed=proposed,advanced=advanced,balanced=balanced)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--self-check',action='store_true');args=parser.parse_args()
    if args.self_check:self_check();return
    selection_path=HERE/'combined-selection-protocol.json';protocol=json.loads(selection_path.read_text())
    assert protocol['analyzer_sha256']==hashed(__file__)
    assert len(protocol['runs'])==10 and not(HERE/'joint-development.json').exists()
    rows=[];candidates=[];bindings={};run_audits=[];traces_count=proposed_total=advanced_total=0
    for spec in protocol['runs']:
        run=ROOT/spec['path'];report=json.loads((run/'report.json').read_text());recipe=json.loads((run/'recipe.json').read_text())
        assert report['completed'] and not report.get('error') and hashed(run/'recipe.json')==report['recipe_sha256']
        assert hashed(run/'source.zip')==report['source_zip_sha256']
        source_protocol=HERE/spec['protocol'];assert hashed(source_protocol)==protocol['training_protocol_sha256'][spec['protocol']]
        declared=json.loads(source_protocol.read_text());assert recipe['protocol']==declared
        assert recipe['arm']==spec['arm'] and recipe['seed']==spec['seed'] and recipe['actual_steps']==declared['steps']==102400
        assert declared['development_seeds']==protocol['development_seeds'] and declared['evaluate_at']==protocol['checkpoints_evaluated']
        assert declared['future_confirmation_seeds']==protocol['confirmation']['nominal_seeds']
        assert [e['step'] for e in report['evaluations']]==declared['evaluate_at']
        assert [c['step'] for c in report['checkpoints']]==list(range(0,102401,25600))
        with zipfile.ZipFile(run/'source.zip') as archive:
            assert sha256(archive.read('confidence/run-joint-stage.py')).hexdigest()==recipe['source']['driver']
            assert sha256(archive.read('confidence/joint-protocol.json')).hexdigest()==hashed(source_protocol)
            for path,pin in recipe['inputs'].items():
                assert hashed(path)==pin
                assert sha256(archive.read('confidence/inputs/'+Path(path).name)).hexdigest()==pin
            for group in ('swing','angle_error'):
                source=recipe['source']['robust'][group]
                for relative,pin in source['code_sha256'].items():
                    member=posixpath.normpath('src/cartpole_sdk/'+relative)
                    assert sha256(archive.read(member)).hexdigest()==pin
        for cp in report['checkpoints']:
            path=run/cp['path'];assert path.parent.resolve()==(run/'checkpoints').resolve() and hashed(path)==cp['sha256']
        for name in ('recipe.json','report.json','source.zip'):bindings[str((run/name).relative_to(ROOT))]=hashed(run/name)
        for evaluation in report['evaluations']:
            path=run/evaluation['path'];assert hashed(path)==evaluation['sha256'];result=json.loads(path.read_text())
            assert result['completed'];evaluation_recipe=json.loads((path.parent/'recipe.json').read_text())
            assert hashed(path.parent/'recipe.json')==result['recipe_sha256']
            assert evaluation_recipe['seeds']==protocol['development_seeds'] and evaluation_recipe['seconds']==25
            cp=next(c for c in report['checkpoints'] if c['step']==evaluation['step']);assert evaluation_recipe['checkpoint_sha256']==cp['sha256']
            episodes=result['episodes'];assert len(episodes)==4
            assert {(e['seed'],e['start']) for e in episodes}=={(s,t) for s in (95000,95001) for t in ('hanging','upright')}
            for e in episodes:
                assert e['scenario']=='nominal'
                audit=trace_audit(path.parent/e['trace_path'],e,25);traces_count+=1;proposed_total+=audit['proposed'];advanced_total+=audit['advanced']
            for start in ('hanging','upright'):
                group=[e for e in episodes if e['start']==start]
                rows.append(dict(group=spec['group'],arm=spec['arm'],optimizer_seed=spec['seed'],step=evaluation['step'],start=start,episodes=len(group),holds=sum(e['hold_success'] for e in group),full_balance=sum(e['balanced_fraction']>=1.-1e-12 for e in group),faults=sum(e['fault_reason'] is not None for e in group),captures=[e['first_one_second_capture_s'] for e in group],mean_balanced_fraction=float(np.mean([e['balanced_fraction'] for e in group])),mean_longest_dwell_s=float(np.mean([e['longest_balance_dwell_s'] for e in group])),worst_max_abs_x_m=max(e['max_abs_x_m'] for e in group),tail_x_rms_m=[e['final_window_x_rms_m'] for e in group]))
            eligible,rank=rank_episodes(episodes)
            candidates.append(dict(group=spec['group'],optimizer_seed=spec['seed'],run=spec['path'],step=evaluation['step'],checkpoint=cp,eligible=eligible,rank=rank,development_evaluation_sha256=evaluation['sha256']))
        run_audits.append(dict(run=spec['path'],completed=True,checkpoints=len(report['checkpoints']),development_evaluations=len(report['evaluations']),recipe_sha256=report['recipe_sha256'],source_zip_sha256=report['source_zip_sha256'],inputs=recipe['inputs'],training_objective=recipe.get('training_objective','finite-dwell'),policy_std=declared['policy_std']))
    eligible=[c for c in candidates if c['eligible']];selected=max(eligible,key=lambda c:tuple(c['rank'])) if eligible else None
    initial_hashes=sorted({c['checkpoint']['actor_weights_sha256'] for c in candidates if c['step']==0});assert len(initial_hashes)==1
    groups=[]
    for label in ('ppo','retained','continuing','low-std'):
        for step in protocol['checkpoints_evaluated']:
            for start in ('hanging','upright'):
                chosen=[r for r in rows if r['group']==label and r['step']==step and r['start']==start]
                values=[v for r in chosen for v in r['tail_x_rms_m']]
                groups.append(dict(group=label,step=step,start=start,optimizer_seeds=[r['optimizer_seed'] for r in chosen],episodes=sum(r['episodes'] for r in chosen),holds=sum(r['holds'] for r in chosen),full_balance=sum(r['full_balance'] for r in chosen),faults=sum(r['faults'] for r in chosen),mean_balanced_fraction=float(np.mean([r['mean_balanced_fraction'] for r in chosen])),mean_longest_dwell_s=float(np.mean([r['mean_longest_dwell_s'] for r in chosen])),worst_max_abs_x_m=max(r['worst_max_abs_x_m'] for r in chosen),mean_tail_x_rms_m=float(np.mean(values)) if all(v is not None for v in values) else None))
    result=dict(schema='cartpole-joint-development-selection-v2',created_utc=datetime.now(timezone.utc).isoformat(),hardware_accepted=False,selection_protocol_sha256=hashed(selection_path),rows=rows,groups=groups,candidates=candidates,selected=selected,selection=protocol['selection'],tie_break=protocol['tie_break'],confirmation=protocol['confirmation'],analyzer_sha256=hashed(__file__),run_audits=run_audits,source_bindings=bindings,initial_actor_hashes=initial_hashes,training_decisions=1024000,development_episodes=traces_count,development_proposed_decisions=proposed_total,development_advanced_decisions=advanced_total,limitations=protocol['limitations'],confirmation_outcomes_used_for_selection=False)
    write_new(HERE/'joint-development.json',result)
    with (HERE/'joint-development.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(groups[0]));writer.writeheader();writer.writerows(groups)
    os.environ.setdefault('MPLCONFIGDIR','/tmp/cartpole-confidence-mpl')
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained');colors={'ppo':'#b45309','retained':'#0f766e','continuing':'#7c3aed','low-std':'#2563eb'}
    for spec in protocol['runs']:
        label=f"{spec['group']} / {spec['seed']}";style={11:'-',23:'--',47:':'}[spec['seed']]
        hang=[r for r in rows if r['group']==spec['group'] and r['optimizer_seed']==spec['seed'] and r['start']=='hanging'];up=[r for r in rows if r['group']==spec['group'] and r['optimizer_seed']==spec['seed'] and r['start']=='upright']
        for ax,vals,metric in [(axes[0,0],hang,'holds'),(axes[0,1],up,'full_balance'),(axes[1,0],hang,'mean_longest_dwell_s'),(axes[1,1],up,'worst_max_abs_x_m')]:
            y=[r[metric]/r['episodes'] if metric in ('holds','full_balance') else r[metric]*1000 if metric=='worst_max_abs_x_m' else r[metric] for r in vals]
            ax.plot([r['step'] for r in vals],y,marker='o',linestyle=style,color=colors[spec['group']],alpha=.8,label=label)
    for ax,title,ylabel in zip(axes.flat,['Hanging final holds','Upright uninterrupted balance','Hanging longest continuous dwell','Upright worst cart displacement'],['Fraction of two poses','Fraction of two poses','Mean seconds','Millimeters']):ax.set(title=title,xlabel='Online decisions',ylabel=ylabel);ax.grid(alpha=.2)
    axes[0,0].set_ylim(-.05,1.05);axes[0,1].set_ylim(-.05,1.05);axes[1,1].axhline(120,color='#64748b',linestyle='--',lw=1)
    axes[1,0].legend(fontsize=8,ncol=2);fig.suptitle('Ten-run development comparison • selection frozen before confirmation',fontsize=14)
    fig.supxlabel('Common development poses 95000 / 95001. Ablations have two optimizer seeds; original arms have three. Initial actor is shared.',fontsize=9)
    fig.savefig(HERE/'joint-development.png',dpi=180);plt.close(fig)
    print(json.dumps(dict(selected=selected,groups=groups,development_episodes=traces_count,training_decisions=1024000),indent=2))
if __name__=='__main__':main()
