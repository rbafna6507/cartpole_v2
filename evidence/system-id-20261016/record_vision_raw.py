"""Bounded, read-only raw sensing-stream recorder; never opens serial or calibrates."""
import argparse,hashlib,json,math,time,urllib.request
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--seconds',type=float,required=True);a=p.parse_args()
 if not 1<=a.seconds<=240:raise ValueError('duration must be 1..240 seconds')
 a.directory.mkdir(parents=True,exist_ok=True);out=a.directory/'vision.ndjson';report={'source':'http://127.0.0.1:3090/api/sensing-stream?max_hz=100','started_ns':time.monotonic_ns(),'requested_s':a.seconds,'frames':0,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()};stop=a.directory/'stop-recording';end=time.monotonic()+a.seconds
 try:
  with out.open('xb') as f, urllib.request.urlopen(report['source'],timeout=2) as stream:
   previous=None
   while time.monotonic()<end and not stop.exists():
    line=stream.readline(4*1024*1024+1)
    if not line:raise RuntimeError('sensing stream ended')
    if len(line)>4*1024*1024 or not line.endswith(b'\n'):raise ValueError('invalid sensing record bound')
    row=json.loads(line)
    if row.get('schema')!='cartpole-sensing-stream-v1':raise ValueError('unexpected sensing schema')
    f.write(line);report['frames']+=1
    vision=row['vision'];t=vision.get('t')
    if isinstance(t,(float,int)) and math.isfinite(t):
     if 'first_camera_t' not in report:report['first_camera_t']=t
     report['last_camera_t']=t
    if previous is not None and row['stream_seq']<=previous:raise ValueError('non-increasing stream sequence')
    previous=row['stream_seq']
 except BaseException as exc:report['failure']=repr(exc);raise
 finally:
  report['finished_ns']=time.monotonic_ns()
  if out.exists():report['bytes']=out.stat().st_size;report['sha256']=hashlib.sha256(out.read_bytes()).hexdigest()
  (a.directory/'vision-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
