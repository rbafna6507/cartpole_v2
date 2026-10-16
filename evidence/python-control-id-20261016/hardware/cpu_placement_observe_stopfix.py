"""One disabled-only experiment; restore every surviving thread's prior affinity."""
import os,json,time,subprocess,traceback
from pathlib import Path
main=int(subprocess.check_output(['systemctl','--user','show','cartpole-vision.service','-p','MainPID','--value'],text=True))
if main<=1:raise RuntimeError('vision service not running')
pids={main}
for _ in range(6):
 before=len(pids)
 for p in Path('/proc').iterdir():
  if p.name.isdecimal():
   try:
    stat=(p/'stat').read_text().rsplit(')',1)[1].split()
    if int(stat[1]) in pids:pids.add(int(p.name))
   except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 if len(pids)==before:break
report={'case':'cpu-placement-observe','vision_main':main,'processes':sorted(pids),'saved':{},'applied':{},'restored':{},'restore_missing':[],'restore_errors':{},'new_threads_restored':{}}
root=Path('/home/rbafna/cartpole-v2-runs/python-id-20261016')/('cpu-placement-'+str(time.time_ns()));root.mkdir()
try:
 for pid in sorted(pids):
  if (Path('/proc')/str(pid)).stat().st_uid!=os.getuid():raise RuntimeError('refuse other-user process')
  for t in (Path('/proc')/str(pid)/'task').iterdir():
   tid=int(t.name);mask=os.sched_getaffinity(tid);new=mask-{2}
   if not new:raise RuntimeError('thread has no alternate CPU')
   if mask!=set(range(6)):raise RuntimeError('requires uniform original six-CPU affinity for restoration')
   report['saved'][str(tid)]=sorted(mask)
   os.sched_setaffinity(tid,new);report['applied'][str(tid)]=sorted(os.sched_getaffinity(tid))
 cmd=['taskset','-c','2','/home/rbafna/cartpole_v2/.venv/bin/python','/home/rbafna/cartpole-v2-live/staging/python-feedback-20261016/diagnose_timing_stopfix.py','observe','--sdk-src','/home/rbafna/cartpole-v2-live/staging/python-feedback-20261016/src','--seconds','20','--rate','250','--switch-interval','.001']
 report['command']=cmd;r=subprocess.run(cmd,capture_output=True,text=True,timeout=40);report.update(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
 print(r.stdout,flush=True)
 if r.returncode:raise RuntimeError('observation diagnostic failed')
except BaseException as exc:
 report['failure']=repr(exc);report['traceback']=traceback.format_exc();raise
finally:
 for tid,mask in report['saved'].items():
  try:os.sched_setaffinity(int(tid),set(mask));report['restored'][tid]=sorted(os.sched_getaffinity(int(tid)))
  except ProcessLookupError:report['restore_missing'].append(tid)
  except OSError as exc:report['restore_errors'][tid]=str(exc)
 for pid in sorted(pids):
  tasks=Path('/proc')/str(pid)/'task'
  if tasks.exists():
   for task in tasks.iterdir():
    if task.name not in report['saved']:
     try:
      os.sched_setaffinity(int(task.name),set(range(6)));report['new_threads_restored'][task.name]=sorted(os.sched_getaffinity(int(task.name)))
     except ProcessLookupError:pass
     except OSError as exc:report['restore_errors'][task.name]=str(exc)
 report['vision_main_after']=int(subprocess.check_output(['systemctl','--user','show','cartpole-vision.service','-p','MainPID','--value'],text=True))
 (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({'report':str(root/'report.json'),'restored':len(report['restored']),'missing':report['restore_missing']}),flush=True)
