from pathlib import Path
import csv,hashlib,json,math
root=Path(__file__).resolve().parents[2];src=root/'logs/run_20260916_153109.csv';data=src.read_bytes()
rows=[{k:float(v) for k,v in r.items()} for r in csv.DictReader(data.decode().splitlines())]
windows=[]
for lo,hi,name in [(0,120,'12/12/60'),(151,188,'16/16/70'),(200,206,'16/16/100'),(214,258,'16/16/50'),(273,312,'20/16/40')]:
    item={'settings_swing_balance_jerk':name,'window_s':[lo,hi]}
    for label,modes in [('balance',[3]),('rail_recovery',[5,6])]:
        selected=[r for r in rows if lo<=r['t_ms']/1000<=hi and r['mode'] in modes]
        if selected:
            peak=max(selected,key=lambda r:abs(r['accel']))
            item[label]={'peak_abs_acceleration':abs(peak['accel']),'board_s':peak['t_ms']/1000}
    windows.append(item)
report={'source_sha256':hashlib.sha256(data).hexdigest(),'source':str(src),'note':'Recorded commands, not measured cart acceleration. Windows exclude parameter-change boundaries. First window includes manual balance and automatic swing-up.','windows':windows,'ideal_stops_from_0p8_zero_accel':[{'jmax':j,'stop_distance_mm':1000*2/3*.8*math.sqrt(2*.8/j),'peak_acceleration':math.sqrt(2*.8*j)} for j in [40,60,70,100]]}
Path(__file__).with_name('evidence.json').write_text(json.dumps(report,indent=2)+'\n')
