#!/usr/bin/env python3
"""Offline timing evidence only. Does not import Rig or open any transport."""
import argparse,hashlib,json,math,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('trial',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
rows=[json.loads(line) for line in next(a.trial.glob('rig-*.jsonl')).read_text().splitlines()]
timing=json.loads((a.trial/'timings.json').read_text());report=json.loads((a.trial/'report.json').read_text())
states=[r for r in rows if r['type']=='state'];active=[r for r in states if r['state']['mode']==12 and not r['state']['fault']]
requests=[r for r in rows if r['type']=='action_request'];failures=[r for r in rows if r['type']=='policy_failure'];faults=[r for r in states if r['state']['fault']]
lookup={r['state']['tick']:r['state'] for r in active}
assert all(r['request']['acceleration_m_s2']==0 for r in requests)
assert len(requests)==len(timing['computes'])
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def stats(xs):
 return dict(n=len(xs),median=statistics.median(xs),max=max(xs),min=min(xs),mean=statistics.mean(xs)) if xs else None
compute=[]
for request,t in zip(requests,timing['computes']):
 q=request['request'];s=lookup[q['observation_sequence']]
 compute.append(dict(sequence=q['sequence'],observation_tick=q['observation_sequence'],receipt_to_compute_start_ms=(t[0]-s['received_ns'])/1e6,compute_wall_ms=(t[1]-t[0])/1e6,compute_thread_cpu_ms=t[2]/1e6,compute_wall_minus_thread_cpu_ms=(t[1]-t[0]-t[2])/1e6))
writes=[]
for t in timing['writes']:
 writes.append(dict(start_host_ns=t[0],finish_host_ns=t[1],thread=t[3],payload=t[4],wall_ms=(t[1]-t[0])/1e6,thread_cpu_ms=t[2]/1e6,wall_minus_thread_cpu_ms=(t[1]-t[0]-t[2])/1e6))
result=dict(schema='cartpole-offline-zero-timing-v1',input_sha256={p.name:digest(p) for p in sorted(a.trial.glob('*')) if p.is_file()},source_sha256=digest(Path(__file__)),report=report,first_active=active[0],last_active=active[-1],last_request=requests[-1],failure=failures[-1] if failures else None,first_fault=faults[0] if faults else None,compute_by_action=compute,transport_writes=writes,compute_summary={k:stats([v[k] for v in compute]) for k in ['receipt_to_compute_start_ms','compute_wall_ms','compute_thread_cpu_ms','compute_wall_minus_thread_cpu_ms']},write_summary={k:stats([v[k] for v in writes]) for k in ['wall_ms','thread_cpu_ms','wall_minus_thread_cpu_ms']},motion=dict(step_estimate_range_m=[min(r['state']['x'] for r in active),max(r['state']['x'] for r in active)],encoder_angle_range_deg=[math.degrees(min(r['state']['theta'] for r in active)),math.degrees(max(r['state']['theta'] for r in active))]))
if faults:
 f=faults[0]['state'];last=active[-1];q=requests[-1]['request']
 result['last_action_expiry_tick']=q['observation_sequence']+(q['expires_at_ns']-q['issued_at_ns'])//1000000
 result['fault_elapsed_since_first_enabled_s']=(f['tick']-active[0]['state']['tick'])/1000
 result['last_good_state_receipt_to_fault_receipt_ms']=(f['received_ns']-last['state']['received_ns'])/1e6
 result['last_good_state_receipt_to_state_record_ms']=(last['host_monotonic_ns']-last['state']['received_ns'])/1e6
 result['accepted_but_uncomputed_tick']=last['state']['tick'] if last['state']['tick']!=q['observation_sequence'] else None
 result['interpretation']=[
  'The final healthy state is recorded after _accept assigns _state and calls notify_all under the shared condition lock. Therefore its wake predicate existed by the state-record timestamp.',
  'The final failure stage is wait and no compute follows that healthy state. Scheduling, GIL availability or condition-lock reacquisition can explain the missed opportunity; the existing timestamps do not identify which.',
  'The predicate check and Condition.wait use the same RLock as state assignment and notify_all. No unlocked check-to-sleep lost-notification race is visible in the inspected implementation.',
  'Publisher submit only replaces one snapshot reference. Its worker performs asdict/json/UDP on the same interpreter. Logger JSON serialization and flush also run on a worker. Both can compete for the GIL, but this trace does not show either causing this stall.',
  'The final inference and transport write completed before the unconsumed state arrived. This failure does not require motor motion, slow inference or a long final transport write.',
  'The prior learned trial stalled after inference before its command record; this zero-action trial stalls before the next inference. They demonstrate at least two locations where host timing can consume the replacement margin.'
 ]
root=Path(__file__).resolve().parents[3]
result['inspected_source_sha256']={str(path.relative_to(root)):digest(path) for path in [root/'src/cartpole_sdk/rig/client.py',root/'src/cartpole_sdk/rig/policy.py',root/'src/cartpole_sdk/rig/transport.py',root/'src/cartpole_sdk/sensing/telemetry.py',root/'src/cartpole_sdk/recording.py']}
result['proposed_instrumentation']={
 'boundary_only_driver':'Temporary trusted experiment driver instrumentation; keep production files, actor,20ms leases,100Hz telemetry and physical parameters unchanged.',
 'events':['Rig.wait_state entry/exit/failure with after_tick and returned tick','Condition.notify_all timestamp while _state tick is known, and Condition.wait entry/return after lock reacquisition','policy act entry/exit and Rig.step entry/exit','_send entry, write-lock acquired, transport.write entry/exit and command record timestamp'],
 'event_fields':['monotonic_ns','thread_time_ns','thread native id','board tick/action sequence','primitive stage code'],
 'recording':'Append primitive tuples into bounded per-thread in-memory buffers; no JSON serialization, file writes, printing or stack sampling in the hot path. Flush only after explicit stop.',
 'comparison':'The ongoing switch-interval1ms vs5ms zero-emission comparison preserves leases and separates interpreter scheduling sensitivity from physical control. Report exposed action counts, worst notify-to-wait-return and receipt-to-command delay, not just pass/fail. One pass is not a runtime guarantee.',
 'if_not_resolved':'Measure OS wakeup/scheduling trace for control and IO native thread ids during another separately authorized zero-emission run to distinguish runnable-but-not-scheduled delay from GIL/lock waiting. Optionally compare publisher enabled/disabled as a single-variable follow-up while retaining recorder evidence; do not infer causality from coincidence.'
}
a.output.mkdir(parents=True,exist_ok=False)
(a.output/'analysis.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
(a.output/'analyzer.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({k:result.get(k) for k in ['fault_elapsed_since_first_enabled_s','last_good_state_receipt_to_fault_receipt_ms','last_good_state_receipt_to_state_record_ms','accepted_but_uncomputed_tick','motion','compute_summary','write_summary']},indent=2))
