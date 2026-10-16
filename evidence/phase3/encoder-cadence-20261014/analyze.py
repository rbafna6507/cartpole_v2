import json, math, statistics, sys
from collections import Counter
for name in sys.argv[1:]:
    rows=[json.loads(s)['state'] for s in open(name) if '"type":"state"' in s]
    active=[s for s in rows if s['flags']&2 and s['mode']==2]
    periods=[]; previous=None; last_change=None; changed=0
    for s in active:
        if previous is None or s['tick']-previous['tick']>30:
            last_change=s['tick']
        elif s['theta']!=previous['theta']:
            periods.append(s['tick']-last_change);last_change=s['tick'];changed+=1
        previous=s
    print(json.dumps({'file':name,'active_samples':len(active),'change_period_ticks':Counter(periods).most_common(12), 'changed_fraction':changed/max(1,len(active)), 'range':{k:[min(s[k] for s in active),max(s[k] for s in active)] for k in ['theta','omega','x','velocity','acceleration','demand']} if active else {},'period_median':statistics.median(periods) if periods else None},indent=2))
