from pathlib import Path
import csv,hashlib,json,statistics
root=Path(__file__).resolve().parents[2]
src=root/'logs/run_20260916_153109.csv'; data=src.read_bytes()
rows=[{k:float(v) for k,v in r.items()} for r in csv.DictReader(data.decode().splitlines())]
episodes=[]
for i,r in enumerate(rows):
    if not i or r['t_ms']<90000 or r['mode']!=3 or rows[i-1]['mode'] not in (2,5,6): continue
    j=i+1
    while j<len(rows) and rows[j]['mode']==3: j+=1
    if j==len(rows):continue
    episodes.append({'first_sample_s':r['t_ms']/1000,'sampled_duration_s':(rows[j]['t_ms']-r['t_ms'])/1000,'next_mode':int(rows[j]['mode'])})
report={'source':str(src),'sha256':hashlib.sha256(data).hexdigest(),'rows':len(rows),'last_board_s':rows[-1]['t_ms']/1000,'note':'25 Hz sampled episode lengths, not exact 1 kHz transition times. Very short captures may be absent. x is pulse-inferred; v/a are commands.','episodes':episodes,'count':len(episodes),'median_duration_s':statistics.median(e['sampled_duration_s'] for e in episodes),'rail_brake_exits':sum(e['next_mode']==5 for e in episodes),'swingup_exits':sum(e['next_mode']==2 for e in episodes)}
Path(__file__).with_name('metrics.json').write_text(json.dumps(report,indent=2)+'\n')
print({k:v for k,v in report.items() if k!='episodes'})
