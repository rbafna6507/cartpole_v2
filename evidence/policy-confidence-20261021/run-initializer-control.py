#!/usr/bin/env python3
"""Post-selection, pre-outcome-declared paired initializer control; no reselection."""
from datetime import datetime,timezone
from hashlib import sha256
import csv,importlib.util,json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'runs/policy-confidence-20261021/joint-confirmation'
ENV=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def write(p,d):
    with Path(p).open('x') as f:json.dump(d,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def main():
    protocol=load(HERE/'initializer-control-extension.json');assert digest(__file__)==protocol['runner_sha256']
    assert digest(OUT/'selection-frozen.json')==protocol['selection_sha256']
    began=time.time()
    while not all((OUT/(mode+'-command-receipt.json')).exists() for mode in ('nominal','sdk')):
        if (OUT/'failure.json').exists():raise RuntimeError('Main confirmation failed; control not started')
        if time.time()-began>7200:raise TimeoutError('Nominal and SDK processes did not finish')
        time.sleep(10)
    for mode in ('nominal','sdk'):assert load(OUT/(mode+'-command-receipt.json'))['returncode']==0
    # Main runner can now have only its one queued stress job running.
    command=[str(ROOT/'.venv/bin/python'),str(HERE/'run-confirmation.py'),str(ROOT/protocol['run']),'--step','0','--output',str(OUT/'initializer-nominal'),'--mode','nominal','--seconds','60','--seeds',*[str(x) for x in protocol['seeds']]]
    write(OUT/'initializer-control-command.json',command);started=time.time();print('START initializer nominal control',flush=True)
    with (OUT/'initializer-control.stdout.log').open('x') as stdout,(OUT/'initializer-control.stderr.log').open('x') as stderr:r=subprocess.run(command,cwd=ROOT,env=ENV,stdout=stdout,stderr=stderr)
    receipt=dict(returncode=r.returncode,elapsed_seconds=time.time()-started,command_sha256=digest(OUT/'initializer-control-command.json'),stdout_sha256=digest(OUT/'initializer-control.stdout.log'),stderr_sha256=digest(OUT/'initializer-control.stderr.log'))
    write(OUT/'initializer-control-command-receipt.json',receipt);print(json.dumps(receipt),flush=True)
    if r.returncode:raise RuntimeError('Initializer control failed; preserve logs')
    root=OUT/'initializer-nominal';binding=load(root/'binding.json');report=load(root/'evaluation/report.json');evaluation_recipe=load(root/'evaluation/recipe.json');completion=load(root/'receipt.json')
    assert binding['step']==0 and binding['checkpoint']==protocol['checkpoint'] and binding['mode']=='nominal' and binding['seconds']==60 and binding['seeds']==protocol['seeds']
    assert report['completed'] and completion['completed']
    assert digest(root/'binding.json')==completion['binding_sha256'] and digest(root/'evaluation/report.json')==completion['report_sha256']
    assert digest(root/'evaluation/recipe.json')==report['recipe_sha256'] and evaluation_recipe['checkpoint_sha256']==protocol['checkpoint']['sha256']
    assert {(e['seed'],e['start']) for e in report['episodes']}=={(s,t) for s in protocol['seeds'] for t in ('hanging','upright')} and len(report['episodes'])==16
    while not (HERE/'joint-confirmation-summary.json').exists():
        if (OUT/'failure.json').exists():raise RuntimeError('Main confirmation analysis failed; control preserved')
        if time.time()-began>7200:raise TimeoutError('Main analysis did not complete')
        time.sleep(10)
    spec=importlib.util.spec_from_file_location('confirmation_audit',HERE/'analyze-confirmation.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    selected=load(HERE/'joint-confirmation-summary.json');assert selected['selection_sha256']==protocol['selection_sha256']
    selected_report=load(OUT/'nominal/evaluation/report.json');rows=[];paired=[]
    for ep in report['episodes']:
        row,truth,obs=audit.audit_episode('nominal',root/'evaluation',ep,60);rows.append(row)
        final=next(r for r in selected['episodes'] if r['mode']=='nominal' and r['seed']==ep['seed'] and r['start']==ep['start'])
        other=next(e for e in selected_report['episodes'] if e['seed']==ep['seed'] and e['start']==ep['start'])
        first=json.loads((OUT/'nominal/evaluation'/other['trace_path']).open().readline())
        match=ep['initial_state']==other['initial_state'] and obs==first['actor_observation'];assert match
        pair=dict(seed=ep['seed'],start=ep['start'],initial_state_and_observation_equal=match)
        for key in ('hold_success','full_balance','balanced_fraction','first_one_second_capture_s','longest_balance_dwell_s','final_window_x_rms_m','max_abs_x_m','raw_action_change_rms_m_s2','rapid_capture_and_30s_dwell'):
            pair['initial_'+key]=row[key];pair['selected_'+key]=final[key]
        paired.append(pair)
    groups=[]
    for label,episodes in [('initial',rows),('selected',[r for r in selected['episodes'] if r['mode']=='nominal'])]:
        for start in ('hanging','upright'):
            rr=[r for r in episodes if r['start']==start];captures=[r['first_one_second_capture_s'] for r in rr]
            groups.append(dict(checkpoint=label,start=start,episodes=len(rr),holds=sum(r['hold_success'] for r in rr),full_balance=sum(r['full_balance'] for r in rr),faults=sum(r['fault'] is not None for r in rr),captures=sum(c is not None for c in captures),mean_capture_s_all_episodes=audit.mean(captures),mean_capture_s_among_captured=audit.mean([c for c in captures if c is not None]),mean_balanced_fraction=audit.mean([r['balanced_fraction'] for r in rr]),mean_longest_dwell_s=audit.mean([r['longest_balance_dwell_s'] for r in rr]),mean_final_window_x_rms_m=audit.mean([r['final_window_x_rms_m'] for r in rr]),worst_max_abs_x_m=max(r['max_abs_x_m'] for r in rr),mean_raw_action_change_rms_m_s2=audit.mean([r['raw_action_change_rms_m_s2'] for r in rr]),rapid_capture_and_30s_dwell=sum(r['rapid_capture_and_30s_dwell'] for r in rr)))
    transitions=[]
    for start in ('hanging','upright'):
        rr=[p for p in paired if p['start']==start]
        transitions.append(dict(start=start,gained_holds=sum(not r['initial_hold_success'] and r['selected_hold_success'] for r in rr),lost_holds=sum(r['initial_hold_success'] and not r['selected_hold_success'] for r in rr),both_hold=sum(r['initial_hold_success'] and r['selected_hold_success'] for r in rr),neither_hold=sum(not r['initial_hold_success'] and not r['selected_hold_success'] for r in rr)))
    result=dict(schema='cartpole-initializer-paired-confirmation-v1',extension_protocol_sha256=digest(HERE/'initializer-control-extension.json'),selection_sha256=protocol['selection_sha256'],control_checkpoint=protocol['checkpoint'],selected=selected['selected'],groups=groups,transitions=transitions,paired=paired,initial_episodes=rows,control_report_sha256=digest(root/'evaluation/report.json'),selected_summary_sha256=digest(HERE/'joint-confirmation-summary.json'),audited_control_episodes=len(rows),advanced_control_decisions=sum(r['advanced'] for r in rows),candidate_selection_changed=False,hardware_accepted=False,limitations=['Control was declared after development selection but before this analyst inspected any selected reserved-pose outcomes.','Same eight paired poses; not sixteen independent hanging samples.','Policy actions change trajectories and environmental random-number consumption may diverge despite paired pose/reset seeds.','No alternate candidate may be selected from these control results.'])
    write(HERE/'initializer-control-comparison.json',result);write(OUT/'initializer-control-comparison.json',result)
    with (HERE/'initializer-control-paired.csv').open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=list(paired[0]));w.writeheader();w.writerows(paired)
    print(json.dumps(dict(groups=groups,transitions=transitions),indent=2),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as exc:
        write(OUT/'initializer-control-failure.json',dict(error=repr(exc),traceback=traceback.format_exc()));raise
