#!/usr/bin/env python3
"""Read sealed campaigns and summarize observed host timing, never physical delay.

Usage: python analyze_timing.py --input SEALED_DIR [--input SEALED_DIR] --output NEW_DIR
No hardware/network operations or source mutation. Failed recordings remain failed.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path

from cartpole_sdk.identification.campaign import verify, _read_json, _read_lines
from cartpole_sdk.identification.timing_capture import summarize_timing, _stats


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def state_kind(state):
    if state.get('fault', 0):
        return 'faulted'
    if state.get('flags', 0) & 2:
        return 'active_external' if state.get('mode') in (1, 12) else 'active_native'
    return 'stopped'


def state_intervals(records):
    """Classify adjacent original snapshots before filtering, so no gap is bridged."""
    groups = defaultdict(list)
    duplicates = defaultdict(int)
    previous = None
    for record in records:
        if record.get('type') != 'state':
            continue
        state = record['state']
        if previous is not None and state['sid'] == previous['sid']:
            kind = state_kind(state) if state_kind(state) == state_kind(previous) else 'transitions'
            board = (state['unwrapped_us']-previous['unwrapped_us'])/1000
            receipt = (state['received_ns']-previous['received_ns'])/1e6
            if board == 0:
                duplicates[kind] += 1
            elif board > 0 and receipt >= 0:
                groups[kind].append(dict(previous_tick=previous['unwrapped_tick'],
                    tick=state['unwrapped_tick'], received_ns=state['received_ns'],
                    board_gap_ms=board, receipt_gap_ms=receipt,
                    receipt_gap_minus_board_gap_ms=receipt-board))
        previous = state
    result = {}
    for kind in ('active_external','active_native','stopped','faulted','transitions'):
        rows = groups[kind]
        result[kind] = dict(
            receipt_gap_ms=_stats([r['receipt_gap_ms'] for r in rows]),
            board_gap_ms=_stats([r['board_gap_ms'] for r in rows]),
            receipt_gap_minus_board_gap_ms=_stats([r['receipt_gap_minus_board_gap_ms'] for r in rows]),
            duplicate_board_snapshots=duplicates[kind],
            intervals_over_15ms=sum(r['receipt_gap_ms']>15 for r in rows),
            intervals_at_least_20ms=sum(r['receipt_gap_ms']>=20 for r in rows),
            worst_intervals=sorted(rows,key=lambda r:r['receipt_gap_ms'],reverse=True)[:5])
    return result


def pipeline_samples(records):
    """Join each action to its actual source snapshot and preceding matching write."""
    states = {}; writes = {}; policies = {}; trial_id = None; result = []
    for record in records:
        kind = record.get('type')
        if kind == 'campaign_trial_start':
            trial_id = record['trial']['id']; writes.clear(); policies.clear()
        elif kind == 'policy_start':
            writes.clear(); policies.clear()
        elif kind == 'state':
            state = record['state']
            states.setdefault((state['sid'],state['unwrapped_tick']),state)
        elif kind == 'timing_policy_end':
            policies[record['observation_sequence']] = record
        elif kind == 'timing_transport_write_end':
            command = record.get('command') or {}
            if command.get('verb') in ('A','V'):
                writes[(command['sid'],command['sequence'])] = record
        elif kind == 'action_request':
            request = record['request']; sid = int(request['session_id'])
            state = states.get((sid,request['observation_sequence']))
            write = writes.get((sid,request['sequence']))
            if state is None or write is None:
                continue
            policy = policies.get(request['observation_sequence'])
            received, start, end = state['received_ns'],write['host_start_ns'],write['host_end_ns']
            result.append(dict(trial_id=trial_id,sequence=request['sequence'],
                observation_tick=request['observation_sequence'], source_received_ns=received,
                issued_at_board_ns=request['issued_at_ns'],expires_at_board_ns=request['expires_at_ns'],
                ttl_ms=(request['expires_at_ns']-request['issued_at_ns'])/1e6,
                write_start_ns=start,write_end_ns=end,write_complete=write['complete'],
                receipt_to_write_start_ms=(start-received)/1e6,
                receipt_to_write_end_ms=(end-received)/1e6,
                write_duration_ms=(end-start)/1e6,
                receipt_to_policy_start_ms=None if policy is None else (policy['host_start_ns']-received)/1e6,
                policy_duration_ms=None if policy is None else (policy['host_end_ns']-policy['host_start_ns'])/1e6))
    return result


def compact_timing(records):
    result = summarize_timing(records)
    samples = result['acknowledgements'].pop('samples')
    result['acknowledgements']['receipt_elapsed_lower_ms'] = _stats([
        s['receipt_elapsed_lower_ns']/1e6 for s in samples if s['status']=='observed'])
    result['acknowledgements']['receipt_elapsed_upper_ms'] = _stats([
        s['receipt_elapsed_upper_ns']/1e6 for s in samples if s['status']=='observed'])
    result['acknowledgements']['per_action_samples_omitted'] = len(samples)
    return result


def summarize_gc(probe):
    """Pair observed GC callbacks on their host clock without inferring delays."""
    starts = {}; intervals = []
    for stamp,phase,generation,collected,uncollectable in probe['events']:
        if phase=='start' and generation not in starts:
            starts[generation]=stamp
        elif phase=='stop' and generation in starts and stamp>=starts[generation]:
            start=starts.pop(generation)
            intervals.append(dict(generation=generation,start_ns=start,end_ns=stamp,
                duration_ms=(stamp-start)/1e6,collected=collected,uncollectable=uncollectable))
        else:
            raise ValueError('unpaired or reversed GC callback pair')
    if starts:raise ValueError('incomplete GC callback pair')
    return dict(duration_ms_by_generation={str(g):_stats([s['duration_ms'] for s in intervals if s['generation']==g])
        for g in sorted({s['generation'] for s in intervals})},intervals=intervals,
        thresholds=probe.get('thresholds'),
        interpretation='Callback elapsed wall time for this process only; not a physical transport or actuator delay measurement.')


def summarize_pipeline(samples):
    fields = ('receipt_to_policy_start_ms','policy_duration_ms','receipt_to_write_start_ms',
              'receipt_to_write_end_ms','write_duration_ms')
    result = {k:_stats([s[k] for s in samples if s[k] is not None]) for k in fields}
    # Action sequence numbers restart at each policy lease; never bridge trials.
    result['inter_action_write_start_ms'] = _stats([(b['write_start_ns']-a['write_start_ns'])/1e6
        for a,b in zip(samples,samples[1:]) if a['trial_id']==b['trial_id'] and b['sequence']==a['sequence']+1])
    result['ttl_values_ms'] = sorted({s['ttl_ms'] for s in samples})
    result['worst_receipt_to_write'] = sorted(samples,key=lambda s:s['receipt_to_write_end_ms'],reverse=True)[:5]
    return result


def fault_reconstruction(records, pipeline):
    states = [r['state'] for r in records if r.get('type')=='state']
    first = next((i for i,s in enumerate(states) if s.get('fault')),None)
    if first is None:
        return None
    fault = states[first]; previous = states[first-1] if first else None
    recent = [s for s in pipeline if s['source_received_ns']<=fault['received_ns']][-5:]
    accepted = next((s for s in reversed(recent) if previous and s['sequence']==previous['last_seq']),None)
    selected = states[max(0,first-5):first+3]
    origin = selected[0]['received_ns']; events = []
    for state in selected:
        events.append(dict(event='state receipt',host_ns=state['received_ns'],
            tick=state['unwrapped_tick'],last_seq=state['last_seq'],fault=state['fault'],mode=state['mode']))
    for sample in recent:
        for point in ('start','end'):
            events.append(dict(event='action write '+point,host_ns=sample['write_'+point+'_ns'],
                sequence=sample['sequence'],observation_tick=sample['observation_tick']))
    for event in events:
        event['host_relative_ms'] = (event['host_ns']-origin)/1e6
    return dict(first_fault_code=fault['fault'],first_fault_tick=fault['unwrapped_tick'],
        first_fault_received_ns=fault['received_ns'],last_healthy_tick=None if previous is None else previous['unwrapped_tick'],
        last_observed_action_before_fault=accepted,
        fault_minus_last_observed_action_anchor_ticks=None if accepted is None else fault['unwrapped_tick']-accepted['observation_tick'],
        recent_actions=recent,timeline=sorted(events,key=lambda e:e['host_ns']),
        interpretation='Fault 1 is ACTION_EXPIRED in executor_core.h. A complete host write does not establish board receipt/acceptance time. Tick-anchored expiry and late receipt/dispatch are observable; physical one-way or actuator latency is not.')


def analyze(root):
    root = Path(root).resolve(); ok,reason = verify(root)
    if not ok:
        raise ValueError(reason)
    report = _read_json(root/'report.json')
    raw = root/report['raw_log']
    if raw.parent != root:
        raise ValueError('raw log must be directly inside sealed source')
    records = list(_read_lines(raw)); pipeline = pipeline_samples(records)
    trials = []
    for trial in report['trials']:
        subset = [r for r in records if trial['started_ns']<=r.get('host_monotonic_ns',-1)<=trial['finished_ns']]
        samples = [s for s in pipeline if s['trial_id']==trial['id']]
        trials.append(dict(id=trial['id'],kind=trial['kind'],completed=trial['completed'],
            reference=trial.get('trial'),failure=trial.get('failure'),state_intervals=state_intervals(subset),
            action_pipeline=summarize_pipeline(samples),timing=compact_timing(subset)))
    return dict(name=root.name,source_path=str(root),source_sha256=dict(manifest=digest(root/'manifest.json'),
        report=digest(root/'report.json'),raw=digest(raw)),
        collection={k:report.get(k) for k in ('dataset_role','sensor_mode','runtime','completed','stop_confirmed',
            'last_disabled_snapshot','failure','records_dropped','pending_log_records','timing_record_errors')},
        timing=compact_timing(records),state_intervals=state_intervals(records),
        action_pipeline=summarize_pipeline(pipeline),trials=trials,
        fault=fault_reconstruction(records,pipeline))


def draw(runs,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,5.2),layout='constrained')
    colors=['#1766a0','#d56720','#3b7e4f','#93478b','#5a6270','#c27a00']
    for i,run in enumerate(runs):
        active=run['state_intervals']['active_external']['receipt_gap_ms']
        if not active['count']:
            continue  # Native-only runs remain separate in the full report.
        stopped=run['state_intervals']['stopped']['receipt_gap_ms']
        values=[active['p50'],active['p95'],active['p99'],active['max'],stopped['max']]
        axes[0].plot(range(5),values,'o-',color=colors[i%len(colors)],label=run['name'])
    axes[0].set_xticks(range(5),['Active P50','Active P95','Active P99','Active max','Stopped max'],rotation=20)
    axes[0].set(ylabel='Host receipt interval (ms)',title='Active timing separated from stopped diagnostics')
    axes[0].axhline(20,color='red',ls='--',lw=1,label='20 ms lease duration (different clock basis)')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    fault=next((r['fault'] for r in runs if r['fault']),None)
    if fault:
        timeline=fault['timeline']; offset=timeline[0]['host_relative_ms']; state_index=0
        for event in timeline:
            if event['event']=='state receipt' and event['fault'] and event['tick']!=fault['first_fault_tick']:
                continue
            t=event['host_relative_ms']-offset
            if event['event']=='state receipt':
                y=1; label=f"tick {event['tick']%1000}\nseq {event['last_seq']}"+('\nFAULT' if event['fault'] else '')
                color='red' if event['fault'] else '#1766a0'
                label_offset=8+32*(state_index%2);state_index+=1
            else:
                y=0 if event['event'].endswith('start') else -.15
                label=str(event['sequence']) if y==0 else '';color='#d56720';label_offset=7
            axes[1].plot(t,y,'o',color=color)
            if label:axes[1].annotate(label,(t,y),xytext=(0,label_offset),textcoords='offset points',ha='center',fontsize=7)
        axes[1].margins(x=.08)
        axes[1].set(ylim=(-.4,1.8),yticks=[0,1],yticklabels=['Action write','State receipt'],
                    xlabel='Relative host time (ms)',title='Expiry sequence: host receipt/write events')
        axes[1].grid(alpha=.2)
    fig.savefig(output/'timing.png',dpi=150);plt.close(fig)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',action='append',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--no-plot',action='store_true')
    parser.add_argument('--gc-events',action='append',type=Path,default=[])
    args=parser.parse_args(argv); output=args.output.resolve()
    if output.exists():raise FileExistsError(output)
    if any(p.resolve()==output or p.resolve() in output.parents for p in args.input):
        raise ValueError('output must be outside sealed sources')
    runs=[analyze(p) for p in args.input]
    probes=[dict(source_path=str(p.resolve()),source_sha256=digest(p),
        **summarize_gc(_read_json(p))) for p in args.gc_events]
    result=dict(schema='cartpole-host-timing-diagnostic-v1',hardware_accepted=False,
        physical_one_way_latency_identified=False,script_sha256=digest(__file__),runs=runs,gc_probes=probes,
        interpretation=[
            'Receipt gaps are classified on adjacent source snapshots before any state filtering. Stopped periods and transition intervals are separate.',
            'Same-source repeated board snapshots are counted separately and excluded from periodic interval percentiles.',
            'Receipt-to-write intervals include host decoding/scheduling/policy/transport overhead after State.received_ns; they omit preceding board-to-host age.',
            'Acknowledgement bounds are host-write to first exact last_seq receipt, not board acceptance or physical latency. Raw source logs retain every action.',
            'Failed collection and STOP status are preserved. CPU-affinity effects require new labeled repeats; these data alone do not establish causation.',
            'A quiet feedback policy does not measure the deployed neural actor inference cost. Keep the 20 ms lease and existing SDK cadence rejection unchanged.'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    if not args.no_plot:draw(runs,output)
    print(json.dumps(dict(output=str(output),runs=[dict(name=r['name'],collection=r['collection'],
        active_receipt_gap_ms=r['state_intervals']['active_external']['receipt_gap_ms'],
        stopped_receipt_gap_ms=r['state_intervals']['stopped']['receipt_gap_ms'],
        action_pipeline={k:v for k,v in r['action_pipeline'].items() if k!='worst_receipt_to_write'},
        fault=None if not r['fault'] else {k:v for k,v in r['fault'].items() if k not in ('timeline','recent_actions')}) for r in runs]),indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
