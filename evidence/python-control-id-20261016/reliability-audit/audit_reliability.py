"""Read-only audit of recorded Python AUTO actions and native comparison.

All policy equations import the previously frozen capture-audit source.  No
Rig, transport, serial, parameter-write or live-hardware API is imported.
"""
import argparse, collections, dataclasses, gzip, hashlib, json, math
import statistics, subprocess, sys, tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
EVIDENCE = BASE.parent
FROZEN = EVIDENCE / 'capture-audit'
sys.path.insert(0, str(FROZEN / 'source'))
from cartpole_sdk.contracts import Sample, Observation, Session, UNITS
from cartpole_sdk.control.parameters import ControllerParameters, gains
from cartpole_sdk.control.reference import balance, approach, can_capture
from cartpole_sdk.control.forecast import can_capture_fast
from cartpole_sdk.control.motion import State, advance, settled_velocity_accel
from cartpole_sdk.policies.executor_feedback import ExecutorFeedbackPolicy


def stats(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs: return {'n': 0}
    return dict(n=len(xs), min=xs[0], max=xs[-1], mean=statistics.mean(xs),
                rms=math.sqrt(statistics.mean(x*x for x in xs)),
                p50=statistics.median(xs), p95=xs[min(len(xs)-1, int(.95*len(xs)))])


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mode_intervals(transitions, end_ns):
    """Half-open intervals; never extrapolate first capture through later swing."""
    return [dict(mode=t['mode'], start_ns=t['board_ns'],
                 end_ns=transitions[i+1]['board_ns'] if i+1<len(transitions) else end_ns,
                 duration_s=((transitions[i+1]['board_ns'] if i+1<len(transitions) else end_ns)-t['board_ns'])/1e9)
            for i,t in enumerate(transitions)]


def obs(s, request):
    t=s['unwrapped_us']*1000
    quantities=('position','velocity','angle','angular_velocity','acceleration','brake_direction')
    values=(s['x'],s['velocity'],s['angle_hat'],s['omega'],s['acceleration'],s['brake_direction'])
    samples=tuple(Sample('pole' if q in ('angle','angular_velocity') else 'cart',q,
        'magnetic_filtered' if q=='angle' else 'magnetic' if q=='angular_velocity' else 'step',
        float(value),UNITS[q],'encoder-zero' if q in ('angle','angular_velocity') else 'cart-step-home',
        'recorded','valid',None,'estimated',t,t,t) for q,value in zip(quantities,values))
    samples+=(Sample('pole','angle','magnetic',s['theta'],'rad','encoder-zero','recorded','valid',None,'measured',t,t,t),)
    return Observation(request['session_id'],request['clock_id'],s['unwrapped_tick'],t,
                       'board acquisition snapshot proxy',samples)


def capture_forecast(p,k,s):
    q,w,x,v,a=[s[z] for z in ('angle_hat','omega','x','velocity','acceleration')]
    initial=9.81/p.leff*q*q+w*w
    motion=State(v,a);trace=[]
    for i in range(36):
        request=balance(k,q,w,x,motion.velocity)
        motion=advance(motion,x,request,min(p.vmax,p.vmax_b),p.amax_b,max(p.amax_s,p.amax_b),p.jmax,p.rail,.005,rail_margin=p.rail_margin)
        x+=motion.velocity*.005
        alpha=(9.81*math.sin(q)-motion.acceleration*math.cos(q))/p.leff
        q=math.atan2(math.sin(q+w*.005+.5*alpha*.005**2),math.cos(q+w*.005+.5*alpha*.005**2))
        w+=alpha*.005
        trace.append(dict(t_s=(i+1)*.005,q=q,w=w,x=x,v=float(motion.velocity),a=float(motion.acceleration)))
    return dict(initial_metric=initial,final_metric=9.81/p.leff*q*q+w*w,
                allowed_final_metric=initial*1.05+.01,trajectory=trace)


def native_oracle(p,states):
    names=list(dataclasses.asdict(p))
    # The frozen native Parameters struct has exactly the user-tunable names.
    names=[n for n in names if n not in ('rail_hard_limit',)]
    with tempfile.TemporaryDirectory(prefix='cartpole-offline-oracle-') as temp:
        d=Path(temp);cpp=d/'oracle.cpp';exe=d/'oracle'
        cpp.write_text('#include <iostream>\n#include "swing_controller.h"\nint main(){swing_control::Parameters p;float q,w,x,v,a;while(std::cin'+''.join(' >> p.'+n for n in names)+' >> q >> w >> x >> v >> a){auto k=swing_control::gains(p);std::cout<<swing_control::canCapture(p,k,q,w,x,v,a)<<"\\n";}}\n')
        subprocess.run(['c++','-std=c++17','-O2','-fno-fast-math','-I',str(FROZEN/'headers'),str(cpp),'-o',str(exe)],capture_output=True,text=True,check=True)
        lines=[' '.join(format(v,'.17g') for v in [*(getattr(p,n) for n in names),*(s[z] for z in ('angle_hat','omega','x','velocity','acceleration'))]) for s in states]
        out=subprocess.run([str(exe)],input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True)
    return [bool(int(x)) for x in out.stdout.splitlines()]


def motion_hold(p,s,request):
    """Four 1 ms governor steps, constant demand; not a physical counterfactual."""
    m=State(s['velocity'],s['acceleration']);x=s['x']
    for _ in range(4):
        m=advance(m,x,request,min(p.vmax,p.vmax_b),p.amax_b,max(p.amax_s,p.amax_b),p.jmax,p.rail,.001,rail_margin=p.rail_margin)
        x+=m.velocity*.001
    return dict(v=float(m.velocity),a=float(m.acceleration),x=x)


def audit_python(run):
    report_path=run/'report.json';report=json.loads(report_path.read_text());log=next(run.glob('rig-*.jsonl.gz'))
    raw=gzip.decompress(log.read_bytes());events=[json.loads(line) for line in raw.splitlines()]
    allstates=[e['state'] for e in events if e['type']=='state'];states={s['unwrapped_tick']:s for s in allstates}
    actions=[e for e in events if e['type']=='action_request'];trans=[e for e in events if e['type']=='policy_transition']
    commands={int(e['payload'].split()[3]):e for e in events if e['type']=='command' and e['payload'].startswith('V2 A ')}
    ack={}
    for s in allstates:
        if s['last_seq'] and s['last_seq'] not in ack: ack[s['last_seq']]=s
    p=ControllerParameters(**report['parameters']);k=gains(p)
    first=obs(states[actions[0]['request']['observation_sequence']],actions[0]['request'])
    policy=ExecutorFeedbackPolicy(tuple(x.channel for x in first.samples[:6]),parameters=p,rate_hz=250,start_mode='auto',raw_angle_channel=first.samples[-1].channel)
    policy.reset(Session(first.session_id,first.clock_id))
    t0=first.available_ns
    end=actions[-1]['request']['issued_at_ns']+4_000_000
    intervals=mode_intervals(trans,end)
    oracle=native_oracle(p,[states[e['request']['observation_sequence']] for e in actions])
    rows=[];mismatches=[];shadow_errors=[]
    for i,e in enumerate(actions):
        req=e['request'];s=states[req['observation_sequence']]
        q,w,x,v,a=[s[z] for z in ('angle_hat','omega','x','velocity','acceleration')]
        b=balance(k,q,w,x,v);intent=policy.act(obs(s,req))
        shadow_errors.append(None if intent is None else intent.acceleration_m_s2-req['acceleration_m_s2'])
        fast=can_capture_fast(p,k,q,w,x,v,a);reference=can_capture(p,k,q,w,x,v,a)
        if not fast==reference==oracle[i]:mismatches.append(dict(index=i,fast=fast,reference=reference,native=oracle[i]))
        limits={}
        for dt in (.001,.004):
            low=settled_velocity_accel(v,a,-min(p.vmax,p.vmax_b),max(p.amax_s,p.amax_b),p.jmax,dt)
            high=settled_velocity_accel(v,a,min(p.vmax,p.vmax_b),max(p.amax_s,p.amax_b),p.jmax,dt)
            limits[str(dt)]=dict(low=float(low),high=float(high),bounded_balance=float(max(low,min(high,max(-p.amax_b,min(p.amax_b,b))))))
        energy=.5*p.leff/9.81*w*w+math.cos(q)-1
        pump=p.ke*energy*math.tanh(w*math.cos(q)/p.phase_soft)-p.kpx*x-p.kdx*v
        pump=max(-p.amax_s,min(p.amax_s,pump))
        approach1=float(approach(p,q,w,x,v,a,pump,.001,k));approach4=float(approach(p,q,w,x,v,a,pump,.004,k))
        ack_s=ack.get(req['sequence']);cmd=commands[req['sequence']]
        row=dict(index=i,t_s=(req['issued_at_ns']-t0)/1e9,tick=s['unwrapped_tick'],mode=policy.mode,
            raw_theta=s['theta'],theta=q,omega=w,x=x,v=v,a=a,balance=b,request=req['acceleration_m_s2'],
            balance_components={key:-getattr(k,'k'+str(j+1))*value for j,(key,value) in enumerate(zip(('theta','omega','x','velocity'),(q,w,x,v)))},
            state_demand=s['demand'],brake=s['brake_direction'],last_seq=s['last_seq'],sequence=req['sequence'],
            capture=fast,limits=limits,approach_1ms=approach1,approach_4ms=approach4,
            receive_to_command_record_ms=(cmd['host_monotonic_ns']-s['received_ns'])/1e6,
            receive_to_request_record_ms=(e['host_monotonic_ns']-s['received_ns'])/1e6,
            first_ack_tick_delta=None if ack_s is None else ack_s['unwrapped_tick']-s['unwrapped_tick'])
        rows.append(row)
    replay_transitions=[dict(board_ns=t0+int(round(r['t_s']*1e9)),mode=r['mode']) for i,r in enumerate(rows) if i==0 or r['mode']!=rows[i-1]['mode']]
    recorded_transitions=[dict(board_ns=t['board_ns'],mode=t['mode']) for t in trans]
    assert replay_transitions==recorded_transitions, 'recorded and replayed mode transitions differ'
    balance_rows=[r for r in rows if r['mode']=='balance']
    captures=[]
    for trans_event in trans:
        if trans_event['mode']!='balance':continue
        s=states[trans_event['observation_sequence']];forecast=capture_forecast(p,k,s)
        target=s['unwrapped_tick']+180
        nearest=min(allstates,key=lambda z:abs(z['unwrapped_tick']-target))
        captures.append(dict(event=trans_event,state=s,forecast=forecast,actual_180ms=nearest,
                             fast=can_capture_fast(p,k,*[s[z] for z in ('angle_hat','omega','x','velocity','acceleration')]),
                             native=oracle[next(i for i,e in enumerate(actions) if e['request']['observation_sequence']==s['unwrapped_tick'])]))
    speedclips=[r for r in balance_rows if abs(r['request']-max(-p.amax_b,min(p.amax_b,r['balance'])))>1e-5]
    hold_effects=[]
    for row in speedclips:
        s=states[row['tick']];host=motion_hold(p,s,row['request']);unbounded=motion_hold(p,s,max(-p.amax_b,min(p.amax_b,row['balance'])))
        hold_effects.append(dict(t_s=row['t_s'],host=host,unbounded=unbounded,delta_a=host['a']-unbounded['a'],delta_v=host['v']-unbounded['v']))
    selected=[r for r in rows if any(c['state']['unwrapped_tick']-100<=r['tick']<=c['state']['unwrapped_tick']+1200 for c in captures)]
    failure=next((e for e in events if e['type']=='policy_failure'),None)
    failure_summary=None
    if failure:
        last=actions[-1];s0=states[last['request']['observation_sequence']]
        fs=states.get(failure.get('failed_observation_sequence'))
        window=[e for e in events if failure['host_monotonic_ns']-40_000_000<=e['host_monotonic_ns']<=failure['host_monotonic_ns']+12_000_000 and e['type'] in ('state','action_request','command','policy_failure','policy_end')]
        subsequent=[s for s in allstates if s['unwrapped_tick']>s0['unwrapped_tick'] and s['received_ns']<failure['host_monotonic_ns']]
        stopped=next((s for s in allstates if s['received_ns']>failure['host_monotonic_ns'] and s['mode']==0),None)
        failure_summary=dict(event=failure,last_action=last,last_state=s0,failed_state=fs,intervening_received_states=subsequent,
            first_stopped_state=stopped,failed_board_gap_ms=None if fs is None else (fs['unwrapped_us']-s0['unwrapped_us'])/1000,
            last_request_record_to_fetch_start_ms=None if 'fetch_started_host_ns' not in failure else (failure['fetch_started_host_ns']-last['host_monotonic_ns'])/1e6,
            gc_overlapping_last_action_to_failure=[g for g in report.get('gc_events',[]) if g['start_ns']<=failure['host_monotonic_ns'] and g['end_ns']>=last['host_monotonic_ns']],
            recorded_gc_events=report.get('gc_events',[]),timeline=window)
    telemetry=[s for s in allstates if first.available_ns<=s['unwrapped_us']*1000<end]
    out=dict(run=run.name,source_manifest=[dict(path=str(report_path),sha256=sha(report_path),remote_path=report['path']+'/report.json'),
        dict(path=str(log),sha256_gzip=sha(log),sha256_uncompressed=hashlib.sha256(raw).hexdigest(),remote_path=report['log'])],
        parameters=dataclasses.asdict(p),gains=dataclasses.asdict(k),before_info=report['before_info'],
        recorded_and_replayed_transitions_identical=True,
        requested_s=report['requested_s'],actions=len(rows),intervals=intervals,
        balance_seconds=sum(i['duration_s'] for i in intervals if i['mode']=='balance'),
        longest_balance_seconds=max([i['duration_s'] for i in intervals if i['mode']=='balance'] or [0]),
        balance_actions=len(balance_rows),balance_raw_theta_rms_deg=math.degrees(stats([r['raw_theta'] for r in balance_rows])['rms']) if balance_rows else None,
        balance_stats={key:stats([r[key] for r in balance_rows]) for key in ('raw_theta','theta','omega','x','v','a','balance','request','receive_to_command_record_ms','first_ack_tick_delta')},
        action_board_intervals_ms=stats([(b['tick']-a['tick']) for a,b in zip(rows,rows[1:])]),
        action_board_interval_counts=dict(collections.Counter(b['tick']-a['tick'] for a,b in zip(rows,rows[1:]))),
        all_action_ack_delta_counts=dict(collections.Counter(r['first_ack_tick_delta'] for r in rows)),
        shadow_max_abs_request_error=max(abs(x) for x in shadow_errors if x is not None),shadow_faults=sum(x is None for x in shadow_errors),
        capture_oracle_disagreements=mismatches,captures=captures,
        speed_clip_count=len(speedclips),first_speed_clip=speedclips[0] if speedclips else None,
        speed_clip_hold_effects=hold_effects,selected_rows=selected,failure=failure_summary,
        events=[e for e in events if e['type'] in ('policy_start','policy_end','policy_transition','termination')],
        telemetry_fault_values=sorted(set(s['fault'] for s in telemetry)),
        telemetry_miss_range=[min(s['misses'] for s in telemetry),max(s['misses'] for s in telemetry)],
        telemetry_drop_range=[min(s['dropped'] for s in telemetry),max(s['dropped'] for s in telemetry)])
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',type=Path,action='append',required=True);ap.add_argument('--native',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():raise SystemExit('refusing to overwrite prior evidence')
    result=dict(schema=1,hardware_activity=False,source_hashes={str(p.relative_to(FROZEN)):sha(p) for root in (FROZEN/'source',FROZEN/'headers') for p in root.rglob('*') if p.is_file() and '__pycache__' not in str(p)},runs=[audit_python(p) for p in args.run])
    if args.native:
        native=json.loads(args.native.read_text());p=ControllerParameters(**native['report']['parameters']);k=gains(p);s=native['transitions'][1]
        native['capture_forecast_from_first_4ms_balance_sample']=capture_forecast(p,k,s)
        native['actual_180ms']=min(native['selected_states'],key=lambda z:abs(z['unwrapped_tick']-s['unwrapped_tick']-180))
        result['native']=native;result['native_compact_sha256']=sha(args.native)
    result['analysis_sha256']=sha(__file__)
    encoded=(json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    args.output.write_bytes(gzip.compress(encoded,mtime=0) if args.output.suffix=='.gz' else encoded)
    print(json.dumps([dict(run=r['run'],actions=r['actions'],balance_s=r['balance_seconds'],balance_rms_deg=r['balance_raw_theta_rms_deg'],shadow_error=r['shadow_max_abs_request_error'],oracle_disagreements=len(r['capture_oracle_disagreements'])) for r in result['runs']],indent=2))

if __name__=='__main__':main()
