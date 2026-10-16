"""Read saved timing columns/report/JSONL; no SDK or hardware imports.

Wall minus main-thread CPU is time not charged to that thread. It includes
intended waits, scheduling/GIL delay, I/O and measurement overhead; it does not
identify a unique cause. Command-log boundaries are logging proxies.
"""
import argparse, bisect, collections, gzip, hashlib, json, math, statistics
from pathlib import Path

FIELDS=('stage','host_start_ns','cpu_start_ns','host_finish_ns','cpu_finish_ns','input_sequence','input_board_ns','output_sequence','output_board_ns','error')
STAGES=('observe','act','step','wait')

def digest(raw):return hashlib.sha256(raw).hexdigest()

def quantiles(xs):
    xs=sorted(xs)
    if not xs:return {'n':0}
    def q(p):
        pos=(len(xs)-1)*p;i=int(pos);j=min(i+1,len(xs)-1)
        return xs[i]+(xs[j]-xs[i])*(pos-i)
    return dict(n=len(xs),min=xs[0],mean=statistics.mean(xs),p50=q(.5),p90=q(.9),p95=q(.95),p99=q(.99),p999=q(.999),max=xs[-1])

def rolling_gap_summary(gaps,window_ns=1_000_000_000):
    pending=collections.deque();maximum=0;worst=[];over_budget=[]
    for gap in gaps:
        now=gap['board_ns']
        while pending and pending[0]['board_ns']<=now-window_ns:pending.popleft()
        pending.append(gap)
        if len(pending)>maximum:
            maximum=len(pending)
            worst=[{k:g[k] for k in ('observation_sequence','board_ns','board_gap_ns')} for g in pending]
        if len(pending)>2:over_budget.append(dict(observation_sequence=gap['observation_sequence'],board_ns=now,count=len(pending)))
    return dict(window_ns=window_ns,window='(now - window_ns, now]',maximum_count=maximum,worst_members=worst,events_exceeding_two=len(over_budget),over_budget_events=over_budget)


def decode_trace(data):
    if tuple(data['fields'])!=FIELDS or tuple(data['stages'])!=STAGES:raise ValueError('unsupported timing schema')
    cols=data['columns'];count=data['count']
    if len(cols)!=len(FIELDS) or any(len(c)!=count for c in cols):raise ValueError('column lengths do not match count')
    result=[]
    for i,values in enumerate(zip(*cols)):
        if any(type(x) is not int for x in values):raise ValueError('trace columns must be integers')
        r=dict(zip(FIELDS,values));r['index']=i
        if r['stage'] not in range(4):raise ValueError('invalid stage')
        if r['host_finish_ns']<r['host_start_ns'] or r['cpu_finish_ns']<r['cpu_start_ns']:raise ValueError('nonmonotonic stage clocks')
        r['name']=STAGES[r['stage']];r['wall_ns']=r['host_finish_ns']-r['host_start_ns'];r['cpu_ns']=r['cpu_finish_ns']-r['cpu_start_ns'];r['wall_minus_cpu_ns']=r['wall_ns']-r['cpu_ns']
        if result and r['host_start_ns']<result[-1]['host_finish_ns']:raise ValueError('unexpected overlapping stage instrumentation')
        result.append(r)
    return result

def compact_row(r):
    return {k:r[k] for k in ('index','name','input_sequence','input_board_ns','output_sequence','output_board_ns','host_start_ns','host_finish_ns','wall_ns','cpu_ns','wall_minus_cpu_ns','error')}

def split_step(row,events):
    """Find log boundaries within step, never equate a log boundary to actuation."""
    inside=[e for e in events if row['host_start_ns']<=e['host_monotonic_ns']<=row['host_finish_ns']]
    action=next((e for e in inside if e['type']=='action_request' and e['request']['observation_sequence']==row['input_sequence']),None)
    command=next((e for e in inside if e['type']=='command' and e.get('payload','').startswith('V2 A ')),None)
    if not action:return None
    result=dict(action_record_ns=action['host_monotonic_ns'],post_action_record_tail_ns=row['host_finish_ns']-action['host_monotonic_ns'],observation_sequence=row['input_sequence'])
    if command:
        result.update(command_record_ns=command['host_monotonic_ns'],pre_command_record_ns=command['host_monotonic_ns']-row['host_start_ns'],command_to_action_record_ns=action['host_monotonic_ns']-command['host_monotonic_ns'],post_command_record_tail_ns=row['host_finish_ns']-command['host_monotonic_ns'])
    return result

def interval(previous,current,rows,event_index=None):
    between=rows[previous['index']+1:current['index']+1]
    wall=current['host_finish_ns']-previous['host_finish_ns'];cpu=current['cpu_finish_ns']-previous['cpu_finish_ns']
    stage=collections.Counter();stage_cpu=collections.Counter();gaps=[];cursor=previous['host_finish_ns'];prior='observe'
    step_splits=[];wait_receipts=[]
    for r in between:
        gaps.append(dict(after_stage=prior,before_stage=r['name'],wall_ns=r['host_start_ns']-cursor))
        stage[r['name']]+=r['wall_ns'];stage_cpu[r['name']]+=r['cpu_ns'];cursor=r['host_finish_ns'];prior=r['name']
        if r['name']=='step' and event_index is not None:
            split=split_step(r,event_index.get(r['input_sequence'],[]))
            if split:step_splits.append(split)
        if r['name']=='wait' and event_index is not None:
            ticks=event_index.get('_state_ticks',[]);saved=event_index.get('_states',[])
            pos=bisect.bisect_right(ticks,r['input_sequence'])
            if pos<len(saved):
                first=saved[pos]
                wait_receipts.append(dict(after_tick=r['input_sequence'],returned_tick=r['output_sequence'],first_newer_tick=first['unwrapped_tick'],first_newer_received_ns=first['received_ns'],wait_start_ns=r['host_start_ns'],wait_finish_ns=r['host_finish_ns'],first_newer_receipt_to_wait_return_ns=r['host_finish_ns']-first['received_ns'],first_newer_receipt_after_wait_start_ns=first['received_ns']-r['host_start_ns']))
    uninstrumented=sum(g['wall_ns'] for g in gaps)
    parts=dict(stage);parts['between_stages']=uninstrumented
    dominant=max(parts,key=parts.get)
    classification=dominant
    if dominant=='step' and step_splits:
        tails=sum(s['post_action_record_tail_ns'] for s in step_splits)
        if tails>=stage['step']/2:classification='step_post_action_record_tail'
    return dict(previous_observation_sequence=previous['output_sequence'],observation_sequence=current['output_sequence'],
        previous_board_ns=previous['output_board_ns'],board_ns=current['output_board_ns'],
        board_gap_ns=current['output_board_ns']-previous['output_board_ns'],
        host_start_ns=previous['host_finish_ns'],host_finish_ns=current['host_finish_ns'],
        host_wall_ns=wall,thread_cpu_ns=cpu,wall_minus_thread_cpu_ns=wall-cpu,
        thread_cpu_fraction=cpu/wall if wall else None,
        dominant_wall_stage=dominant,classification=classification,
        off_thread_cpu_time_dominates=wall>0 and wall-cpu>wall/2,
        stage_wall_ns=dict(stage),stage_cpu_ns=dict(stage_cpu),between_stage_wall_ns=uninstrumented,
        largest_uninstrumented_gap=max(gaps,key=lambda g:g['wall_ns']) if gaps else None,
        step_log_splits=step_splits,wait_receipt_timeline=wait_receipts,stages=[compact_row(r) for r in between])

def analyze(directory,top=12,with_log=True):
    directory=Path(directory);tp=directory/'timing.json';rp=directory/'report.json'
    traw=tp.read_bytes();rraw=rp.read_bytes();trace=json.loads(traw);report=json.loads(rraw);rows=decode_trace(trace)
    provenance=[dict(path=str(p),sha256=digest(raw),bytes=len(raw)) for p,raw in [(tp,traw),(rp,rraw)]]
    event_index=None;log_meta=None;events=[]
    if with_log and report.get('log'):
        name=Path(report['log']).name;log=directory/name
        if not log.exists():log=directory/(name+'.gz')
        if log.exists():
            raw=log.read_bytes();decoded=gzip.decompress(raw) if log.suffix=='.gz' else raw
            events=[json.loads(line) for line in decoded.splitlines()]
            event_index=collections.defaultdict(list);by_action={}
            for e in events:
                if e['type']=='action_request':
                    seq=e['request']['observation_sequence'];event_index[seq].append(e);by_action[e['request']['sequence']]=seq
            for e in events:
                if e['type']=='command' and e.get('payload','').startswith('V2 A '):
                    action_seq=int(e['payload'].split()[3]);seq=by_action.get(action_seq)
                    if seq is not None:event_index[seq].append(e)
            saved=sorted([e['state'] for e in events if e['type']=='state'],key=lambda x:(x['unwrapped_tick'],x['received_ns']))
            event_index['_states']=saved;event_index['_state_ticks']=[x['unwrapped_tick'] for x in saved]
            provenance.append(dict(path=str(log),sha256=digest(raw),sha256_uncompressed=digest(decoded),bytes=len(raw)))
            log_meta=dict(events=len(events),terminations=[e for e in events if e['type']=='termination'])
    observed=[r for r in rows if r['name']=='observe' and not r['error']]
    active=[];excluded=[]
    for i,o in enumerate(observed):
        end=observed[i+1]['index'] if i+1<len(observed) else len(rows)
        acts=[r for r in rows[o['index']+1:end] if r['name']=='act' and r['input_sequence']==o['output_sequence']]
        (active if acts else excluded).append(o)
    intervals=[interval(a,b,rows,event_index) for a,b in zip(active,active[1:])]
    period=1_000_000_000//report['rate_hz']
    long=[x for x in intervals if x['board_gap_ns']>period*3//2]
    stage_summary={}
    for name in STAGES:
        chosen=[r for r in rows if r['name']==name]
        stage_summary[name]=dict(count=len(chosen),errors=sum(r['error']!=0 for r in chosen),
            wall_ms=quantiles([r['wall_ns']/1e6 for r in chosen]),cpu_ms=quantiles([r['cpu_ns']/1e6 for r in chosen]),
            wall_minus_thread_cpu_ms=quantiles([r['wall_minus_cpu_ns']/1e6 for r in chosen]),
            cpu_exceeds_wall_count=sum(r['cpu_ns']>r['wall_ns'] for r in chosen),
            worst_wall=[compact_row(r) for r in sorted(chosen,key=lambda r:r['wall_ns'],reverse=True)[:top]])
    report_keys=('case','seconds','rate_hz','shadow_feedback','log_enabled','mirror_enabled','switch_interval_s','sdk_src','source_sha256','threads_before','threads_after','threads_initial','threads_final','failure','stop_confirmed','stop_state','before_info','timing_summary')
    all_board=[o['output_board_ns'] for o in observed];all_gaps=[b-a for a,b in zip(all_board,all_board[1:])]
    expected=report.get('timing_summary',{})
    summary_consistent=expected.get('observations')==len(observed) and expected.get('max_observation_gap_ns')==max(all_gaps,default=0)
    stage_splits=[split_step(r,event_index.get(r['input_sequence'],[])) for r in rows if r['name']=='step'] if event_index is not None else []
    stage_splits=[s for s in stage_splits if s]
    active_rows=rows[active[0]['index']+1:active[-1]['index']+1] if len(active)>1 else []
    active_stages={name:dict(wall_ms=quantiles([r['wall_ns']/1e6 for r in active_rows if r['name']==name]),cpu_ms=quantiles([r['cpu_ns']/1e6 for r in active_rows if r['name']==name])) for name in STAGES}
    terminal=rows[active[-1]['index']+1:] if active else rows
    return dict(schema=2,hardware_activity=False,run=str(directory),source_manifest=provenance,
        report={k:report[k] for k in report_keys if k in report},trace_count=trace['count'],trace_dropped=trace['dropped'],native_thread_id=trace['native_id'],
        raw_summary_matches_instrumentation=summary_consistent,stage_summary=stage_summary,
        active_interval_stage_summary=active_stages,terminal_stages=[compact_row(r) for r in terminal],
        rolling_long_gaps=rolling_gap_summary(long),
        active_observations=len(active),excluded_unacted_observations=[compact_row(o) for o in excluded],
        active_observation_gap_ms=quantiles([i['board_gap_ns']/1e6 for i in intervals]),
        active_observation_gap_counts_ns=dict(collections.Counter(i['board_gap_ns'] for i in intervals)),
        active_host_interval_ms=quantiles([i['host_wall_ns']/1e6 for i in intervals]),
        active_thread_cpu_interval_ms=quantiles([i['thread_cpu_ns']/1e6 for i in intervals]),
        active_between_stage_wall_ms=quantiles([i['between_stage_wall_ns']/1e6 for i in intervals]),
        long_gap_count=len(long),long_gap_classification_counts=dict(collections.Counter(i['classification'] for i in long)),
        long_gaps_off_thread_cpu_dominated=sum(i['off_thread_cpu_time_dominates'] for i in long),
        worst_intervals_by_wall=sorted(intervals,key=lambda i:i['host_wall_ns'],reverse=True)[:top],
        worst_intervals_by_board_gap=sorted(long,key=lambda i:(i['board_gap_ns'],i['host_wall_ns']),reverse=True)[:top],
        all_long_gap_anchors=[{k:i[k] for k in ('previous_observation_sequence','observation_sequence','board_gap_ns','host_wall_ns','thread_cpu_ns','dominant_wall_stage','classification','off_thread_cpu_time_dominates')} for i in long],
        step_log_split_summary={key.replace('_ns','_ms'):quantiles([s[key]/1e6 for s in stage_splits if key in s]) for key in ('pre_command_record_ns','command_to_action_record_ns','post_command_record_tail_ns','post_action_record_tail_ns')},
        raw_log=log_meta,last_stages=[compact_row(r) for r in rows[-12:]],
        failure_log_timeline=[e for e in events if rows and report.get('failure') and rows[-1]['host_start_ns']-40_000_000<=e['host_monotonic_ns']<=rows[-1]['host_finish_ns']+30_000_000 and e['type'] in ('state','command','reply','action_request','policy_failure','policy_end','stop_failure')],
        limitations=['Thread CPU measures only the instrumented caller, not reader/logger/mirror processes or threads.','Wall minus CPU includes intentional waiting, scheduling, GIL, blocking I/O and clock-call overhead; no unique cause is inferred.','Step split boundaries are host log records, not physical command application times.','Preflight observations not followed by act are excluded from active cadence but listed explicitly.','No hardware, service, SDK or parameter modifications.'])

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path,nargs='+');ap.add_argument('--output',type=Path);ap.add_argument('--top',type=int,default=12);ap.add_argument('--no-log',action='store_true');args=ap.parse_args()
    if args.output and args.output.exists():raise SystemExit('refusing to overwrite evidence')
    if not 1<=args.top<=100:raise SystemExit('top must be 1..100')
    items=[analyze(path,args.top,not args.no_log) for path in args.directory]
    result=items[0] if len(items)==1 else items
    encoded=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.output:args.output.write_text(encoded)
    else:print(encoded,end='')
