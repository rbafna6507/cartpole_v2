"""Read completed native JSONL only; does not import hardware SDK."""
import json,pathlib,hashlib,math,statistics,collections,sys
p=pathlib.Path(sys.argv[1]);rp=p/'report.json';f=next(p.glob('rig-*.jsonl'));r=json.loads(rp.read_text());es=[json.loads(x) for x in f.open()];ss=[e['state'] for e in es if e['type']=='state'];active=[s for s in ss if s['mode'] in (2,3)];t0=active[0]['unwrapped_us'];trans=[];last=None
for s in active:
 if s['mode']!=last:trans.append(s);last=s['mode']
bal=[s for s in active if s['mode']==3];tc=bal[0]['unwrapped_us'] if bal else 0
stats=lambda xs:dict(n=len(xs),min=min(xs),max=max(xs),mean=statistics.mean(xs),rms=math.sqrt(statistics.mean(x*x for x in xs)))
selected=[s for s in active if tc-100000<=s['unwrapped_us']<=tc+1100000]
out=dict(mode_mapping=dict(swing=2,balance=3),source_manifest=[dict(path=str(z),sha256=hashlib.sha256(z.read_bytes()).hexdigest(),bytes=z.stat().st_size) for z in [rp,f]],report={k:v for k,v in r.items() if k not in ('stopped_samples',)},active_start_us=t0,active_end_us=active[-1]['unwrapped_us'],active_count=len(active),transitions=trans,balance_count=len(bal),balance_stats={k:stats([s[k] for s in bal]) for k in ['theta','angle_hat','omega','x','velocity','acceleration','demand']},selected_states=selected,event_types=dict(collections.Counter(e['type'] for e in es)),events=[e for e in es if e['type'] not in ('state','parameter','command','reply')])
print(json.dumps(out,separators=(',',':')))
