"""Lossless selected-column export; original recordings remain unchanged."""
import gzip,hashlib,json,math,sys
from pathlib import Path
p=Path(sys.argv[1]);report=json.loads((p/'report.json').read_text());log=Path(report['log']);vision=p/'vision.ndjson'
skeys=['unwrapped_us','received_ns','tick','theta','angle_hat','omega','x','velocity','acceleration','flags','fault','mode','last_seq']
vkeys=['seq','t','detected','image_angle_rad','pivot_px','bob_px','cart_pivot_px','length_px','confidence','detection_status','status','host_read_to_result_ms']
states=[];frames=[]
for line in log.open():
 row=json.loads(line)
 if row['type']=='state':states.append([row['state'].get(k) for k in skeys])
for line in vision.open():
 row=json.loads(line);frames.append([row['vision'].get(k) for k in vkeys])
result=dict(schema='cartpole-id-column-extract-v1',report=report,vision_report=json.loads((p/'vision-report.json').read_text()),state_columns=skeys,states=states,vision_columns=vkeys,vision=frames,source_hashes={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (log,vision,p/'report.json',p/'vision-report.json')},note='Exact selected original values and clocks, no interpolation or calibration. Full source files retained on Jetson.')
data=json.dumps(result,separators=(',',':'),allow_nan=False).encode();out=p/'columns.json.gz';out.write_bytes(gzip.compress(data,mtime=0))
origin=states[0][0];q=[r[3] for r in states];bins=[]
for start in range(0,math.ceil((states[-1][0]-origin)/1e6),5):
 vals=[r[3] for r in states if start<=(r[0]-origin)/1e6<start+5];angles=[math.atan2(math.sin(v-math.pi),math.cos(v-math.pi)) for v in vals]
 if angles:bins.append([start,round(min(angles),3),round(max(angles),3)])
print(json.dumps(dict(path=str(out),bytes=out.stat().st_size,states=len(states),vision_frames=len(frames),driver_enabled_samples=sum(bool(r[9]&2) for r in states),angle_bins_down_rad=bins)))
