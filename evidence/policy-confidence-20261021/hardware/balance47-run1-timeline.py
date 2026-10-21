#!/usr/bin/env python3
"""Reproduce the run1 expiry/control timeline from immutable local evidence."""
import csv, hashlib, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
TRIAL=ROOT/'runs/policy-confidence-20261021/hardware-live/balance47-run1-01'
OUT=Path(__file__).with_name('balance47-run1-analysis')
trace=next(TRIAL.glob('rig-*.jsonl'))
rows=[json.loads(line) for line in trace.read_text().splitlines()]
a=json.loads((OUT/'analysis.json').read_text())
t=[{k:float(v) for k,v in row.items() if v!=''} for row in csv.DictReader((OUT/'telemetry.csv').open())]
requests=[r for r in rows if r['type']=='action_request']
commands={int(r['payload'].split()[3]):r for r in rows if r['type']=='command' and r['payload'].startswith('V2 A ')}
states=[r['state'] for r in rows if r['type']=='state']
failure=next(r for r in rows if r['type']=='policy_failure')
fault=next(s for s in states if s['fault']==1)
last=requests[-1]; previous=requests[-2]; command=commands[last['request']['sequence']]
begin=a['first_active_state']
def select(row):
 return {k:row[k] for k in ['board_t_s','theta_encoder_deg','observer_rate_rad_s','x_step_estimate_m','commanded_velocity_m_s','accepted_demand_m_s2','governed_acceleration_m_s2','replayed_mlp_m_s2','counterfactual_auto_linear_raw_angle_m_s2']}
result={
 'schema':'cartpole-run1-causal-timeline-v1',
 'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),
 'analysis_sha256':hashlib.sha256((OUT/'analysis.json').read_bytes()).hexdigest(),
 'actor':a['actor'],
 'verdict':'The action replacement deadline explains the abrupt disabled stop at0.510s. It cannot explain the preceding large oscillation. Recovery without the fault is unobserved; inevitable fall or asymptotic instability cannot be claimed.',
 'last_command':command,
 'last_request':last,
 'predecessor_request':previous,
 'policy_failure':failure,
 'first_fault_state':fault,
 'fault_board_elapsed_s':(fault['unwrapped_tick']-begin['unwrapped_tick'])/1000,
 'last_policy_compute_ms':(failure['act_finished_host_ns']-failure['act_started_host_ns'])/1e6,
 'last_inference_end_to_command_record_ms':(command['host_monotonic_ns']-failure['act_finished_host_ns'])/1e6,
 'last_command_record_after_fault_receipt_ms':(command['host_monotonic_ns']-fault['received_ns'])/1e6,
 'predecessor_expiry_tick':previous['request']['observation_sequence']+(previous['request']['expires_at_ns']-previous['request']['issued_at_ns'])//1000000,
 'last_request_expiry_tick':last['request']['observation_sequence']+(last['request']['expires_at_ns']-last['request']['issued_at_ns'])//1000000,
 'initial_nonzero_angle':select(next(r for r in t if abs(r['theta_encoder_deg'])>1)),
 'largest_positive_angle':select(max(t,key=lambda r:r['theta_encoder_deg'])),
 'largest_negative_angle':select(min(t,key=lambda r:r['theta_encoder_deg'])),
 'largest_positive_step_position':select(max(t,key=lambda r:r['x_step_estimate_m'])),
 'last_enabled_state':select(t[-1]),
 'mlp_minus_native_auto_counterfactual_rms_m_s2':math.sqrt(sum((r['replayed_mlp_m_s2']-r['counterfactual_auto_linear_raw_angle_m_s2'])**2 for r in t)/len(t)),
 'governor_reversal_examples':[select(min(t,key=lambda r:abs(r['board_t_s']-s))) for s in [.10,.15,.30,.32]],
 'interpretation':[
  'All51 requests reproduce against the bound actor (max absolute2.6645352591e-15m/s2);50 accepted sequences are observed before the fault.',
  'First -2.285deg encoder change occurs by10ms with zero step displacement and only -0.000893m/s2 demand: this initial input disturbance precedes substantial policy actuation. Release disturbance, encoder behavior and physical zero cannot be separated without independent observations.',
  'At150ms demand+14.5945 but governor+5.2723m/s2; at300ms demand-6.3598 but governor+0.2392m/s2. Recorded jerk150 produces visible actuation-state phase lag during reversals before the expiry.',
  'Angular-rate descriptive lag fit26ms versus centered raw-angle derivative; angle-filter fit2ms. These are diagnostic phase proxies, not identified causal delays or retuning recommendations.',
  'Saved reference537 and I2C error count12 are unchanged. This rules out a recorded reference rewrite or new counted I2C error, not physical calibration bias or all sensor defects.',
  'The final post-inference8.038ms gap is not decomposed into scheduling, request construction, validation, write-lock, transport, or recording. Command timestamps follow write; no wire-time assertion is made.',
  'Position, velocity and acceleration are commanded/step-count states. Physical actuator tracking remains unmeasured until valid independent cart measurements are available.',
  'No production edits, hardware action, training, reserved-pose evaluation or hardware admission.'
 ]
}
assert result['predecessor_expiry_tick']==fault['tick']
assert len(requests)==51 and a['timing']['accepted_sequences_seen']==50
assert abs(a['mlp_replay_minus_requested_m_s2']['max'])<1e-12
assert result['largest_positive_angle']['board_t_s']<result['fault_board_elapsed_s']
assert result['largest_negative_angle']['board_t_s']<result['fault_board_elapsed_s']
for name,h in a['artifacts'].items(): assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==h,name
(OUT/'timeline.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(json.dumps({k:result[k] for k in ['fault_board_elapsed_s','last_policy_compute_ms','last_inference_end_to_command_record_ms','last_command_record_after_fault_receipt_ms','mlp_minus_native_auto_counterfactual_rms_m_s2']},indent=2))
