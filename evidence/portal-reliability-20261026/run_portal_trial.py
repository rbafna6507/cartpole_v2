"""Trusted operator acceptance driver; secrets remain on Jetson outside output."""
import argparse,base64,hashlib,json,time,zipfile
from pathlib import Path
from cartpole_sdk.portal.client import PortalClient
from cartpole_sdk.portal.worker import RemoteQueue
p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('--seconds',type=float,default=2);p.add_argument('--key',required=True);p.add_argument('--source',choices=['simulation','magnetic-step'],default='simulation');p.add_argument('--approve-physical',action='store_true');p.add_argument('--cancel-after',type=float);a=p.parse_args()
if a.source=='magnetic-step' and not a.approve_physical:p.error('explicit operator approval required')
config=Path.home()/'.config/cartpole-portal'
client=PortalClient('http://127.0.0.1:8780',(config/'submit-token').read_text().strip())
operator=RemoteQueue('http://127.0.0.1:8780',(config/'operator-token').read_text().strip())
root=Path.home()/'cartpole-portal/trials-20261026'/a.key;root.mkdir(parents=True,exist_ok=True)
job=client.submit(a.artifact,sensor_source=a.source,duration=a.seconds,idempotency_key=a.key,recording='detailed')
(root/'submitted.json').write_text(json.dumps(job,indent=2))
print(json.dumps({'job':job['id'],'status':job['status'],'artifact':job['artifact']}),flush=True)
if a.source=='magnetic-step' and job['status']=='awaiting_approval':
 reviewed=operator._request('/api/jobs/'+job['id']+'/artifact')
 data=base64.b64decode(reviewed['source_base64'],validate=True)
 assert data==a.artifact.read_bytes() and hashlib.sha256(data).hexdigest()==job['artifact']==reviewed['sha256']
 job=operator._request('/api/jobs/'+job['id']+'/approve',{'artifact':job['artifact'],'sensor_source':job['source'],'duration':job['duration']})
 print(json.dumps({'approved':job['id'],'status':job['status']}),flush=True)
started=None;cancelled=False;last=None;end=time.monotonic()+120
while time.monotonic()<end:
 job=client.get(job['id'])
 if job['status']!=last:print(json.dumps({'status':job['status'],'job':job['id']}),flush=True);last=job['status']
 if job['status']=='running':
  started=started or time.monotonic()
  if a.cancel_after is not None and not cancelled and time.monotonic()-started>=a.cancel_after:
   client.cancel(job['id']);cancelled=True
 if job['status'] in ('succeeded','failed','cancelled'):break
 time.sleep(.2)
else:raise TimeoutError('job did not finish')
(root/'result.json').write_text(json.dumps(job,indent=2))
manifest=client.collect(job['id'],root/'bundle.zip',timeout=60)
job=client.get(job['id']);(root/'result.json').write_text(json.dumps(job,indent=2))
print(json.dumps({'job':job['id'],'status':job['status'],'result':job.get('result'),'manifest_status':manifest['status'],'recording':manifest.get('recording'),'saved':str(root)}),flush=True)
