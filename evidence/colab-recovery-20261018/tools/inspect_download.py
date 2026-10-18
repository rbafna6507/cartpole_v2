#!/usr/bin/env python3
"""Inspect a downloaded training ZIP without extracting it or loading pickled models."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('archive',type=Path)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
result={'archive':str(a.archive),'archive_sha256':hashlib.sha256(a.archive.read_bytes()).hexdigest(),'checkpoints':[]}
with zipfile.ZipFile(a.archive) as z:
    assert z.testzip() is None,'ZIP CRC mismatch'
    for name in z.namelist():
        if not name.endswith('/manifest.json'):continue
        record=json.loads(z.read(name))
        if record.get('schema')!='cartpole-ppo-checkpoint-v1':continue
        content=dict(record);pin=content.pop('content_sha256')
        assert digest(content)==pin,f'manifest hash: {name}'
        for artifact,key in [('checkpoint.zip','checkpoint_sha256'),('actor.json','actor_sha256')]:
            assert hashlib.sha256(z.read(str(Path(name).parent/artifact))).hexdigest()==record[key],name
        result['checkpoints'].append({'path':str(Path(name).parent),'steps':record['timesteps_completed'],'checkpoint_sha256':record['checkpoint_sha256']})
    result['job']=json.loads(z.read('job-status.json'))
    evaluation='runs/ppo-001-heldout.json'
    if evaluation in z.namelist():
        value=json.loads(z.read(evaluation));content=dict(value);pin=content.pop('content_sha256')
        assert digest(content)==pin,'evaluation hash'
        result['evaluation']={k:value[k] for k in ('by_start','hold_successes','episodes_count','mean_score','hold_seconds')}
        for start in ('hanging','upright'):
            rows=[row for row in value['episodes'] if row['start']==start]
            result['evaluation']['by_start'][start]['mean_balanced_fraction']=sum(r['balanced_fraction'] for r in rows)/len(rows)
    else:result['evaluation']=None
with a.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(result,indent=2))
