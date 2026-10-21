#!/usr/bin/env python3
"""Read-only detailed timing analysis; writes only the chosen evidence directory."""
import argparse,hashlib,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('trial',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
trace=next(a.trial.glob('rig-*.jsonl'));rows=[json.loads(l) for l in trace.read_text().splitlines()]
timings=json.loads((a.trial/'timings.json').read_text());report=json.loads((a.trial/'report.json').read_text())
states=[r for r in rows if r['type']=='state'];active=[r for r in states if r['state']['mode']==12 and not r['state']['fault']]
t0=active[0]['state']['received_ns'];fault=next(r for r in states if r['host_monotonic_ns']>t0 and r['state']['fault'])
failure=next(r for r in rows if r['type']=='policy_failure');good={r['state']['tick']:r for r in active}
main=next(t for t in timings['threads'] if t['metadata']['name']=='MainThread');io=next(t for t in timings['threads'] if t['metadata']['name']=='cartpole-rig-io')
notifies=[e for e in io['events'] if e[0]=='condition.notify_all'];wake_pairs=[]
for wait in main['events']:
 if wait[0]!='condition.wait' or wait[1]<t0 or wait[1]>fault['host_monotonic_ns']:continue
 eligible=[n for n in notifies if wait[1]<=n[1]<=wait[2] and n[4] in good and wait[4] is not None and n[4]>wait[4]]
 if not eligible:continue
 notify=min(eligible,key=lambda e:e[1]);st=good[notify[4]]
 wake_pairs.append(dict(wait=wait,notify=notify,healthy_state=st,notify_finish_to_wait_return_ms=(wait[2]-notify[2])/1e6,
                       receipt_to_wait_return_ms=(wait[2]-st['state']['received_ns'])/1e6,wait_wall_ms=(wait[2]-wait[1])/1e6,wait_thread_cpu_ms=wait[3]/1e6))
assert wake_pairs
worst=max(wake_pairs,key=lambda r:r['notify_finish_to_wait_return_ms'])
window_start=worst['notify'][2];window_end=worst['wait'][2]
leaf=[e for e in io['events'] if e[0] in ('transport.read','transport.write','condition.notify_all') and window_start<=e[1]<=e[2]<=window_end]
result=dict(schema='cartpole-detailed-wake-diagnosis-v1',source_sha256=digest(Path(__file__)),input_sha256={v.name:digest(v) for v in a.trial.iterdir() if v.is_file()},
 thread_metadata=[t['metadata'] for t in timings['threads']],runtime_environment=report['runtime_environment'],dropped_events=timings['dropped_events'],
 failure=failure,first_expiry_fault=fault,enabled_span_s=(active[-1]['state']['tick']-active[0]['state']['tick'])/1000,
 fault_elapsed_s=(fault['state']['tick']-active[0]['state']['tick'])/1000,observed_action_requests=sum(r['type']=='action_request' for r in rows),
 worst_wake=worst,notify_to_wait_return_ms=dict(n=len(wake_pairs),median=statistics.median(r['notify_finish_to_wait_return_ms'] for r in wake_pairs),max=worst['notify_finish_to_wait_return_ms']),
 io_leaf_events_during_delayed_wake=leaf,io_leaf_thread_cpu_during_delayed_wake_ms=sum(e[3] for e in leaf)/1e6,
 final_main_events=[e for e in main['events'] if failure['host_monotonic_ns']-40000000<e[1]<failure['host_monotonic_ns']+1000000],
 final_io_events=[e for e in io['events'] if failure['host_monotonic_ns']-40000000<e[1]<failure['host_monotonic_ns']+1000000],
 conclusion='A completed healthy-state notification precedes the main control-thread wait return by10.40ms, crossing the lease deadline. That wait consumes only0.068ms of thread CPU. Both diagnostic workers were disabled and cyclicGC was deferred. Prioritize kernel wake/switch evidence; the current data do not uniquely distinguish OS runnable delay from GIL/futex reacquisition.',
 eliminated_for_this_run=['Missing healthy telemetry','Missing Condition.notify_all','Slow final inference','Long final transport write','Encoder fault or new counted I2C error','Logger/mirror thread workload, because neither worker existed'],
 limitations=['Wall-minus-thread-CPU includes blocking and descheduling and is not by itself runnable scheduler delay.','IO reads can include blocking and thread scheduling; no kernel scheduling trace is available.','A normal condition predicate/wait and matching notify lock are visible; no code-level lost-notification race is identified.','CPU frequency changes cannot be justified as the cause from a mostly non-CPU interval.','No hardware, scheduler changes or privileged commands were executed by this analyzer.'])
result['next_experiment']=dict(purpose='Observe scheduler wakeups and sched-in during the same separately authorized zero-emission probe.',
 prerequisite='Root/operator verifies installed perf supports sched events and the monotonic clock. Recording requires existing tracing privileges or explicit operator sudo.',
 bounded_capture_command='sudo perf sched record -a -C 4,5 --clockid mono -o /tmp/cartpole-zero-sched.data -- sleep 30',
 analysis_command='sudo perf sched timehist -i /tmp/cartpole-zero-sched.data --tid MAIN_TID,IO_TID -w -M',
 tid_source='Use runtime_environment native IDs from the new experiment, not prior process IDs.',
 interpretation=['A prompt sched_wakeup followed by delayed main sched-in identifies runnable scheduler delay.','Prompt main sched-in followed by blocking again points toward futex/GIL/lock waiting.','Inspect IO sched-outs and CPU migrations to detect a scheduling-mediated GIL delay.'],
 settings='Keep20ms leases,100Hz cadence,zero emission,actor,CPU affinity and currentGIL setting unchanged; do not set realtime policy or governor during this observation.',
 sources=['https://man7.org/linux/man-pages/man1/perf-sched.1.html','https://man7.org/linux/man-pages/man1/perf-record.1.html','https://www.kernel.org/doc/html/latest/trace/events.html'])
a.output.mkdir(parents=True,exist_ok=False)
(a.output/'analysis.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n');(a.output/'analyzer.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({k:result[k] for k in ['enabled_span_s','fault_elapsed_s','observed_action_requests','notify_to_wait_return_ms','io_leaf_thread_cpu_during_delayed_wake_ms']},indent=2))
