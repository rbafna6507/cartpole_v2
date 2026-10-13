"""Summarize only the measured trial window, retaining individual balance bouts."""
import csv,json,math
from pathlib import Path
base=Path(__file__).resolve().parents[1]

def bouts(rows, predicate):
 out=[];current=[]
 for row in rows+[None]:
  continuous=not current or (row is not None and 0 < row['t_ms']-current[-1]['t_ms'] <= 150)
  if current and (row is None or not predicate(row) or not continuous):
   duration=(current[-1]['t_ms']-current[0]['t_ms'])/1000
   out.append(dict(duration_s=duration,start_board_ms=current[0]['t_ms'],end_board_ms=current[-1]['t_ms'],angle_rms_deg=math.degrees(math.sqrt(sum(r['theta']**2 for r in current)/len(current))),mean_x_m=sum(r['x'] for r in current)/len(current),max_abs_x_m=max(abs(r['x']) for r in current),exit_mode=None if row is None else row['mode']))
   current=[]
  if row is not None and predicate(row):current.append(row)
 return out

def main():
 reports=[]
 for folder in sorted(base.glob('auto_*')):
  f=next(folder.glob('*.csv'),None)
  if not f or not (folder/'result.json').exists():continue
  result=json.loads((folder/'result.json').read_text())
  if 'start_state' not in result:continue
  begin=result['start_state']['t_ms'];end=result.get('end_of_measurement_state',result.get('final_state',{})).get('t_ms',float('inf'))
  with f.open() as stream:rows=[{k:float(v) for k,v in r.items()} for r in csv.DictReader(stream)]
  rows=[r for r in rows if begin<=r['t_ms']<=end]
  segments=bouts(rows,lambda r:r['mode']==3)
  tight=bouts(rows,lambda r:r['mode']==3 and abs(r['theta'])<math.radians(8) and abs(r['x'])<.15)
  result['balance_segments']=segments
  result['longest_balance_s']=max((x['duration_s'] for x in segments),default=0)
  result['longest_angle_position_hold_s']=max((x['duration_s'] for x in tight),default=0)
  result['total_balance_s']=sum(x['duration_s'] for x in segments)
  result['metric_note']='Filtered to start/end of measurement; contiguous BALANCE bouts split on telemetry gaps >150 ms. Angle-position hold: abs(theta)<8deg, abs(step-derived x)<150mm; no noisy instantaneous rate threshold. Does not prove physical position tracking.'
  reports.append(result)
  print(folder.name,'L',result['parameters'].get('leff'),'bw',result['parameters'].get('bw'),'rail',result['parameters'].get('rail'),'catches',len(segments),'longest',result['longest_balance_s'],'tight',round(result['longest_angle_position_hold_s'],3))
 (base/'trial_comparison.json').write_text(json.dumps(reports,indent=2)+'\n')
if __name__=='__main__':main()
