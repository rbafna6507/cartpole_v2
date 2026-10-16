"""Independently audit saved decision sequences, budgets, bounds and refusals."""
from pathlib import Path
import hashlib
import json
import math
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
r=json.loads((OUT/'results.json').read_text())
p=r['parameters'];checked=0;accepted_long_gaps=0
for relative,digest in r['source_sha256'].items():
    assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
for case in r['cases']:
    rows=json.loads((OUT/f"{case['name']}-decisions.json").read_text())
    accepted=[];long_gaps=[];count=0
    maximum=6_000_000 if case['max_gap_periods'] is None else case['max_gap_periods']*4_000_000
    for row in rows:
        assert row['observation_sequence']*1_000_000==row['board_ns']
        if row['action'] is None:continue
        assert math.isfinite(row['action']) and abs(row['action'])<=max(p['amax_s'],p['amax_b'])
        if accepted:
            delta=row['board_ns']-accepted[-1]
            assert 2_000_000<=delta<=maximum
            long_gaps=[t for t in long_gaps if t>row['board_ns']-1_000_000_000]
            if delta>6_000_000:
                long_gaps.append(row['board_ns']);count+=1
                assert len(long_gaps)<=2
        accepted.append(row['board_ns'])
    assert len(accepted)==case['actions']
    assert count==case['cadence']['accepted_long_gap_count']
    accepted_long_gaps+=count
    if '-rejects-' not in case['name'] and 'no-renewal' not in case['name']:
        assert case['simulated_ns']==case['target_duration_ms']*1_000_000
        assert case['policy_fault'] is None and case['executor_fault'] is None
        assert case['max_abs_x']<p['rail']-p['rail_fault_margin']
        assert case['max_abs_v']<=p['vmax']+2e-6
        assert case['max_abs_acceleration']<=max(p['amax_s'],p['amax_b'])+2e-5
        assert case['max_abs_jerk']<=p['jmax']+.001
    checked+=1
print(f'{checked} saved rollouts audited; {accepted_long_gaps} accepted long gaps; source hashes, replay/budget/rail/velocity/acceleration/jerk checks passed')
