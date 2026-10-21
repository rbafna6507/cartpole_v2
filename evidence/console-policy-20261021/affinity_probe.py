import os,subprocess,json
from pathlib import Path
saved={};base=Path('/proc')
for pid in (264109,264137,264121):
 for p in (base/str(pid)/'task').iterdir():
  tid=int(p.name);saved[tid]=sorted(os.sched_getaffinity(tid))
try:
 for tid in saved:os.sched_setaffinity(tid,{0,1,2,3})
 os.sched_setaffinity(0,{4,5})
 result=subprocess.run(['.venv/bin/python','/tmp/actor_timing_20261021.py','--switch-ms','1','--clear-timeout','--out','runs/console-policy-20261021/actor-zero-affinity-01'])
finally:
 for tid,cpus in saved.items():
  try:os.sched_setaffinity(tid,cpus)
  except ProcessLookupError:pass
 Path('/tmp/affinity-probe-20261021.json').write_text(json.dumps(dict(original_affinities=saved,restored=True))+'\n')
