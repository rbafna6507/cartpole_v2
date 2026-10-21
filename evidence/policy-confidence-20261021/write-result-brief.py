#!/usr/bin/env python3
"""Summarize frozen evidence, including matched optimizer-seed comparisons."""
import csv,json
from hashlib import sha256
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def read(name):return json.loads((HERE/name).read_text())
def write(path,data):
    with path.open('x') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')
def main():
    development=read('joint-development.json');confirmation=read('joint-confirmation-summary.json')
    assert development['selected']==confirmation['selected']
    rows=[]
    for group in ('ppo','retained','continuing','low-std'):
        for step in (0,51200,102400):
            for start in ('hanging','upright'):
                rr=[r for r in development['rows'] if r['group']==group and r['optimizer_seed'] in (11,23) and r['step']==step and r['start']==start]
                assert len(rr)==2
                tails=[v for r in rr for v in r['tail_x_rms_m']]
                rows.append(dict(group=group,step=step,start=start,optimizer_seeds=[11,23],common_pose_seeds=[95000,95001],episodes=sum(r['episodes'] for r in rr),holds=sum(r['holds'] for r in rr),full_balance=sum(r['full_balance'] for r in rr),faults=sum(r['faults'] for r in rr),mean_balanced_fraction=sum(r['mean_balanced_fraction'] for r in rr)/2,mean_longest_dwell_s=sum(r['mean_longest_dwell_s'] for r in rr)/2,worst_max_abs_x_m=max(r['worst_max_abs_x_m'] for r in rr),mean_final_window_x_rms_m=sum(tails)/len(tails) if all(v is not None for v in tails) else None))
    result=dict(schema='cartpole-matched-development-comparison-v1',optimizer_seeds=[11,23],pose_seeds=[95000,95001],note='Outcomes reuse two common poses; the four episodes per row are not four independent physical starts. Shared initial actor is a single control. These descriptive matched comparisons do not alter frozen selection.',development_sha256=sha256((HERE/'joint-development.json').read_bytes()).hexdigest(),rows=rows)
    write(HERE/'joint-development-matched.json',result)
    with (HERE/'joint-development-matched.csv').open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    selected=development['selected'];lines=[f"Frozen selection: {selected['group']} optimizer seed {selected['optimizer_seed']}, step {selected['step']:,}.",f"Checkpoint: {selected['run']}/{selected['checkpoint']['path']}",f"SHA-256: {selected['checkpoint']['sha256']}",'','Development, matched optimizer seeds 11 and 23 (same two poses; descriptive repeated outcomes):']
    for group in ('ppo','retained','continuing','low-std'):
        h=next(r for r in rows if r['group']==group and r['step']==102400 and r['start']=='hanging');u=next(r for r in rows if r['group']==group and r['step']==102400 and r['start']=='upright')
        lines.append(f"  {group}: final hanging holds {h['holds']}/4; upright holds {u['holds']}/4, uninterrupted {u['full_balance']}/4; worst upright displacement {1000*u['worst_max_abs_x_m']:.2f} mm.")
    lines.extend(['','Reserved-pose confirmation, 60 seconds, frozen candidate only:'])
    for g in confirmation['groups']:
        rms='unavailable' if g['mean_final_window_x_rms_m'] is None else f"{1000*g['mean_final_window_x_rms_m']:.3f} mm"
        lines.append(f"  {g['mode']}/{g['scenario']}/{g['start']}: holds {g['holds']}/{g['episodes']}; uninterrupted {g['full_balance']}/{g['episodes']}; faults {g['faults']}; balanced fraction {g['mean_balanced_fraction']:.6f}; tail cart RMS {rms}; worst displacement {1000*g['worst_max_abs_x_m']:.2f} mm; capture <=5 s plus >=30 s dwell {g['rapid_capture_and_30s_dwell']}/{g['episodes']}.")
    sdk=confirmation['sdk_emission'];lines.extend(['',f"SDK same-observation emission parity: {sdk['emission_parity_pass']}; {sdk['compared_actions']} comparisons; maximum discrepancy {sdk['max_abs_raw_discrepancy_m_s2']:.9g} m/s^2 against {sdk['raw_absolute_tolerance_m_s2']} tolerance.",f"Audited {confirmation['audited_episodes']} episodes, {confirmation['advanced_decisions']} physically advanced decisions.",'','Nominal and SDK share eight paired poses; stress scenarios share two other poses. Development selection considered thirty checkpoint records on two poses and can overfit. No reserved outcome changed candidate selection. All evidence is local simulation; hardware performance is separate.'])
    with (HERE/'joint-result-brief.txt').open('x') as f:f.write('\n'.join(lines)+'\n')
    print('\n'.join(lines))
if __name__=='__main__':main()
