"""Summarize frozen offline snapshots; no hardware or transport imports."""
import gzip, hashlib, json, math, platform
from pathlib import Path

BASE = Path(__file__).resolve().parent
def load(name):
    path=BASE/name
    return json.loads(gzip.decompress(path.read_bytes()) if name.endswith('.gz') else path.read_text())

short=load('input.json.gz'); long=load('input-long.json.gz')
short_audit=load('summary.json'); long_audit=load('long-summary.json')
long_details=load('long-sample-diagnostics.json.gz')
last=long['rows'][-1]
failure=next(e for e in long['events'] if e['type']=='policy_failure')
capture=next(e for e in long['events'] if e['type']=='policy_transition' and e['mode']=='balance')
capture_index=next(i for i,r in enumerate(long_details) if r['board_tick']==capture['observation_sequence'])
timeline=[]
previous=None
for event in long['failure_timeline']:
    if event['type']=='state':
        s=event['state']
        if s['unwrapped_tick']<last['state']['unwrapped_tick']-4:continue
        row=dict(type='state',tick=s['unwrapped_tick'],board_us=s['unwrapped_us'],received_ns=s['received_ns'],log_ns=event['host_monotonic_ns'],fault=s['fault'],misses=s['misses'],dropped=s['dropped'],last_seq=s['last_seq'],mode=s['mode'],velocity=s['velocity'],acceleration=s['acceleration'])
        if previous is not None:
            row['board_delta_us']=s['unwrapped_us']-previous['board_us']
            row['host_receive_delta_ms']=(s['received_ns']-previous['received_ns'])/1e6
        previous=row
        timeline.append(row)
    elif event['host_monotonic_ns']>=last['send_record_ns']:
        timeline.append(event)

post=[e for e in timeline if e['type']=='state' and e['tick']>last['state']['unwrapped_tick'] and e['log_ns']<failure['host_monotonic_ns']]
stop=next(e for e in timeline if e['type']=='state' and e['mode']==0)
expiry_tick=last['state']['unwrapped_tick']+(last['request']['expires_at_ns']-last['request']['issued_at_ns'])//1_000_000
capture_state=long_details[capture_index]
balance_states=[r['state'] for r in long['rows'][capture_index:]]
capture_summary=dict(event=capture,diagnostic=capture_state,time_since_first_action_s=(capture['board_ns']-long['rows'][0]['state']['unwrapped_us']*1000)/1e9,
    time_to_last_successful_action_s=(last['state']['unwrapped_us']*1000-capture['board_ns'])/1e9,
    recorded_balance_action_count=len(balance_states),max_abs_filtered_angle=max(abs(s['angle_hat']) for s in balance_states),max_abs_raw_angle=max(abs(s['theta']) for s in balance_states),max_abs_x=max(abs(s['x']) for s in balance_states))

result=dict(source_manifest=long['source_manifest'],last_successful_action=last,failure_event=failure,capture=capture_summary,
    timeline=timeline,pre_failure_new_frames=post,failure_input_candidates=long_audit['failure_candidate_replays'],
    exact_failure_input_logged=False,possible_failure_board_gap_ms=[e['gap_us']/1000 for e in long_audit['failure_candidate_replays'] if e['fault_reason']],
    stop_snapshot_tick=stop['tick'],last_action_expiry_tick=expiry_tick,stop_snapshot_precedes_expiry_ticks=expiry_tick-stop['tick'],
    observed_new_firmware_faults=sorted({e['fault'] for e in timeline if e['type']=='state'}),
    interpretation='All intervening telemetry frames are present at 4 ms board spacing, arriving in a host batch after a 12.895719 ms receipt gap. Latest-state consumption can skip these at the policy layer. Exact failed observation sequence is absent; 8 ms and 12 ms candidates both reproduce the recorded fault. Attribution to USB, OS scheduling, GIL, GC, or another host stall is not determined.',
    limitations=['Host received_ns timestamps are software receipt times, not wire arrival times.','Source analysis assumes the frozen current runner/client behavior matches the staging code used in the trial.','Firmware misses/dropped counters do not measure every possible host scheduling or transport delay.','No serial, service, control, calibration, parameter, or threshold changes were made.'])

assert len(short['rows'])==1248 and len(long['rows'])==1859
assert short_audit['forecast_disagreement_indices']==long_audit['forecast_disagreement_indices']==[]
assert len(short_audit['fast_capture_indices'])==0
assert long_audit['fast_capture_indices'][0]==capture_index==1155
assert [e['tick'] for e in post]==[78917753,78917757,78917761]
assert [e['board_delta_us'] for e in post]==[4000,4000,4000]
assert result['possible_failure_board_gap_ms']==[8.0,12.0]
assert result['stop_snapshot_precedes_expiry_ticks']==1
assert result['observed_new_firmware_faults']==[0]
(BASE/'long-timeline-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')

report='''Offline Python AUTO trial audit, 2026-10-16

RESULT: First 5 s trial had no feasible capture state; long trial captured at
4.619994 s and remained in balance for 2.812 s through its last successful action.
The requested 25 s trial stopped after about 7.44 s on the strict host cadence
guard. This is not a completed 25 s validation. No gates were relaxed.

Both runs used bw=6, ref=330, home_epoch=13, measured span=16502 steps,
rail parameter=.308925003 m, leff=.123999998 m, telemetry=250 Hz.

First trial: all 1,248 acted states were rejected by all three capture oracles:
fast Python, reference Python with binary32 motion, and the actual native C++
header compiled with float state. Zero disagreements and zero initial-guard
passes. Twelve states were inside |filtered angle|<.25 rad (1.164-1.208 s).
At the closest (1.184 s): angle=.002420685, omega=8.964103 rad/s (>3),
x=.1589625 m (>.12), v=.6873906 m/s (>.300000012); applied a=-10.54071,
balance demand=24.221966, mismatch=34.762676 m/s^2 (>4).
This crossing had excess estimated angular energy/rate and infeasible cart
state, not a forecast precision rejection or lack of energy at that crossing.
Later approach bouts only reached |filtered angle|=.3768883 and .5402429.
The energy estimates depend on the configured, not independently validated,
model and do not establish a physical energy or observer calibration result.

Host-dt (.004 s) versus native-dt (.001 s) approach demand differs on recorded
states (maximum difference 11.388667 m/s^2 in the first run), particularly at
the settled-velocity branch boundary. This can change a physical trajectory;
the shadow comparison does not prove that it caused the unsuccessful first
attempt. Missing 1 ms observations cannot be reconstructed exactly.

Long trial: all 1,859 acted states produced matching capture decisions across
the three implementations (166 accepted, including states already balancing).
The first initial-guard pass was the recorded capture: tick 78914937,
q=.2264062, omega=-1.062245, x=-.0156, v=-.2826185,
applied a=5.377762, balance demand=1.493028465, mismatch=3.884733535 (<4).
Before that sample, velocity and acceleration mismatch blocked the immediate
approach. The current policy shadow reproduced all successful actions to
2.22e-15 with no replay faults, ending in balance.

Cadence failure: last successful action 1859 used tick 78917749.
Frame 78917753 followed at a 4 ms board interval but a 12.895719 ms host
receipt interval. Frames 78917757 and 78917761 followed only .894573 ms and
.788045 ms later in host time, also at 4 ms board intervals. All three are in
the log before the failure. Their firmware misses/dropped counters were
unchanged and faults remained zero. This is observed host-side delivery or
processing batching, with no missing or duplicate board frame in this interval.

The failure event does not log its observation sequence or board timestamp.
Replaying the next three candidate states from the last successful policy
state accepts +4 ms, and reproduces the recorded cadence fault at +8 and
+12 ms. Thus exact failed input is unidentifiable in this log: tick 78917757
or 78917761 is supported, not an asserted exact 12 ms input jump.
The first stopped snapshot is tick 78917768, one tick before the last action's
expiry at 78917769. No firmware fault was reported. Host policy compute was
.424041 ms mean / 1.515927 ms max; these statistics do not identify the cause
of the separate receive/processing stall.

Next diagnostic: log failed observation sequence/board time and previous
accepted sequence/board time, plus observation fetch and policy start/end
times. Profile receive/buffering/scheduler behavior under the unchanged strict
cadence gate. These data cannot attribute the batch to USB, OS, GIL, or GC.

Provenance/reproduction:
The compact input*.json.gz snapshots contain exact source remote paths, byte
counts and SHA256 hashes. Full raw logs remain remotely at the listed paths;
no giant raw logs copied. source/ and headers/ freeze the analyzed code.
summary.json and long-summary.json include every source hash and full
configuration; sample-diagnostics files contain per-action gate reasons.
long-timeline-summary.json contains exact failure event timeline and replays.

Run from this directory using a Python with the repository dependencies:
PYTHONDONTWRITEBYTECODE=1 /Users/rbafna/projects/cartpole_v2/.venv/bin/python analyze.py
PYTHONDONTWRITEBYTECODE=1 /Users/rbafna/projects/cartpole_v2/.venv/bin/python analyze.py --input input-long.json.gz --prefix long-
PYTHONDONTWRITEBYTECODE=1 /Users/rbafna/projects/cartpole_v2/.venv/bin/python summarize.py
The native oracle requires c++ with C++17 support.

No serial access, service changes, motion commands, deployment, source edits
in the repository, or threshold changes were performed by this analysis.
The C++ oracle is numerical equivalence evidence, not a 1 kHz physical replay.
Reported cart velocity/acceleration are command estimates, not independent
measurements of motor tracking. Host timing is a software logging proxy.
'''
(BASE/'report.txt').write_text(report)
manifest={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(BASE.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json' and '__pycache__' not in p.parts}
(BASE/'artifact-manifest.json').write_text(json.dumps(dict(python=platform.python_version(),files=manifest),indent=2)+'\n')
print(json.dumps(dict(assertions_passed=True,possible_cadence_gaps_ms=result['possible_failure_board_gap_ms'],capture_s=capture_summary['time_since_first_action_s'],balance_through_last_action_s=capture_summary['time_to_last_successful_action_s'],artifacts=len(manifest)),indent=2))
