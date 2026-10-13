import json,time,statistics,pathlib,datetime,traceback
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.client import RigError
PORT='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
root=pathlib.Path.home()/'cartpole-v2-runs'/('executor-stopped-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
root.mkdir(parents=True)
report={'path':str(root),'firmware_hex_sha256':'a53a2f2ab41661a090f36a479e7d68be6d9029d346b73fb54f61da6ad90da964','rates':[]}
try:
 with Rig(PORT,rate_hz=100,log_dir=root,record_capacity=8192) as rig:
  rig.stop()
  info=rig.get_info();report['info']=asdict(info);report['initial']=asdict(rig.state)
  assert info.encoder_upright_raw==3485 and info.reference_saved, 'live calibration changed'
  assert rig.state.healthy and not rig.state.enabled and not rig.state.homed and rig.state.switch_profile, 'unexpected initial safety state'
  for rate in (100,250,500,1000):
   rig.set_rate(rate);time.sleep(.1);rig.records.clear();before=rig.state;began=time.monotonic()
   while time.monotonic()-began<2:
    assert not rig.state.enabled and rig.state.healthy and rig.error is None
    time.sleep(.01)
   records=[r['state'] for r in rig.records if r['type']=='state']
   intervals=[(b['received_ns']-a['received_ns'])/1e6 for a,b in zip(records,records[1:])]
   board=[b['unwrapped_tick']-a['unwrapped_tick'] for a,b in zip(records,records[1:])]
   def pct(xs,p): return sorted(xs)[min(len(xs)-1,int(len(xs)*p))] if xs else None
   report['rates'].append(dict(requested_hz=rate,frames=len(records),receipt_hz=(len(records)-1)/((records[-1]['received_ns']-records[0]['received_ns'])/1e9),receipt_interval_ms=dict(median=statistics.median(intervals),p99=pct(intervals,.99),maximum=max(intervals)),board_delta_ms=dict(median=statistics.median(board),maximum=max(board)),deadline_misses_delta=rig.state.misses-before.misses,dropped_delta=rig.state.dropped-before.dropped,logger_dropped=rig.records_dropped))
  rig.set_rate(0);rig.stop();report['final']=asdict(rig.state);report['final_info']=asdict(rig.get_info());report['ok']=True
except BaseException as exc:
 report['ok']=False;report['error']=repr(exc);report['traceback']=traceback.format_exc()
finally:
 (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2),flush=True)
if not report['ok']:raise SystemExit(1)
