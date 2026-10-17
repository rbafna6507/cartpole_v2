import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'evidence/system-id-20261017/tools/analyze_camera_step_pulses.py'
def tool():
    assert SCRIPT.exists(), 'camera-step diagnostic is not implemented'
    spec=importlib.util.spec_from_file_location('camera_step_pulses',SCRIPT)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_clock_proxy_fits_known_affine_mapping_without_claiming_latency():
    m=tool();b=2000+np.arange(0,4,.01);r=100000+.003+1.00005*(b-b[0])
    mapped,report=m.clock_proxy(b,r)
    assert np.max(abs(mapped-r))<1e-9
    assert report['slope_ppm']==pytest.approx(50,abs=1e-5)
    assert report['calibrated_latency'] is False
    with pytest.raises(ValueError,match='clock'):m.clock_proxy(b[::-1],r)

def test_signed_pixel_gain_and_known_lag_recovered_on_identical_support():
    m=tool();t=np.arange(-.5,4,.01);x=np.where((t>0)&(t<.65),.02*np.sin(np.pi*t/.65)**4,0.)
    vt=np.arange(-.2,1.2,.0125);y=505-900*np.interp(vt-.02,t,x)
    out=m.shape_fit(t,x,vt,y)
    assert out['best_lag_diagnostic']['lag_s']==pytest.approx(.02)
    assert out['best_lag_diagnostic']['gain_px_per_counted_m']==pytest.approx(-900,abs=1e-8)
    assert out['best_lag_diagnostic']['rmse_px']<1e-9
    assert out['zero_lag']['rmse_px']>.1
    assert len({p['samples'] for p in out['lag_sensitivity']})==1

def test_interpolation_never_crosses_board_gap_or_extrapolates():
    m=tool();t=np.array([0.,.01,.02,.1,.11]);x=2*t
    actual=m.interpolate_supported(t,x,np.array([-.01,.005,.02,.05,.1,.2]))
    assert np.isnan(actual[[0,3,5]]).all()
    assert actual[[1,2,4]]==pytest.approx([.01,.04,.2])

def test_camera_uses_raw_pivot_and_reports_missing_not_fused_data():
    m=tool();rows=[]
    for i in range(3):
        rows.append(dict(schema='cartpole-sensing-stream-v1',stream_seq=i,host_t=10+i*.01+.02,
            vision=dict(seq=i,t=10+i*.01,pivot_px=[500+i,200],confidence=.9,detected=True,
                stale=False,worker_error=None,frame_width=960,frame_height=600,length_px=180),
            encoder=dict(theta=999,x=999)))
    rows[1]['vision']['pivot_px']=None
    rows.append(dict(rows[-1],stream_seq=3))
    frames,report=m.camera_frames(rows)
    assert len(frames)==3 and report['duplicate_frames']==1
    assert frames[0]['x_px']==500 and frames[1]['x_px'] is None
    assert report['valid_frames']==2
    broken=[rows[0],dict(rows[1],vision=dict(rows[1]['vision'],t=9.))]
    with pytest.raises(ValueError,match='reversed'):m.camera_frames(broken)


def fixture_run(directory,gz=False):
    import hashlib,gzip,math
    directory.mkdir();origin=2000.;host=100000.;rows=[];vision=[]
    for i in range(450):
        rel=i*.01;t=rel-.5;x=.02*math.sin(math.pi*t/.65)**4 if 0<t<.65 else 0.
        rows.append(dict(type='state',state=dict(sid=7,unwrapped_us=round((origin+rel)*1e6),unwrapped_tick=round((origin+rel)*1000),received_ns=round((host+rel)*1e9),x=x,flags=205,fault=0)))
    rows.insert(0,dict(type='ringdown_reference',board_ns=round((origin+.5)*1e9)))
    for i in range(350):
        rel=i*.0125;t=rel-.5;x=.02*math.sin(math.pi*t/.65)**4 if 0<t<.65 else 0.
        vision.append(dict(schema='cartpole-sensing-stream-v1',stream_seq=i,vision=dict(seq=i,t=host+rel,
            pivot_px=[500+1000*x,200],length_px=180,confidence=.9,detected=True,stale=False,worker_error=None,frame_width=960,frame_height=600)))
    raw=''.join(json.dumps(r)+'\n' for r in rows).encode();camera=''.join(json.dumps(r)+'\n' for r in vision).encode()
    for name,payload in [('rig-test.jsonl',raw),('vision.ndjson',camera)]:
        (directory/(name+('.gz' if gz else ''))).write_bytes(gzip.compress(payload) if gz else payload)
    report=dict(schema='cartpole-id-run-v1',procedure='pulse',completed=True,stop_confirmed=True,records_dropped=0,
        raw_log='rig-test.jsonl',raw_log_sha256=hashlib.sha256(raw).hexdigest(),camera=dict(sha256=hashlib.sha256(camera).hexdigest()),
        result=dict(hold_seconds=3.,amplitude_m=.02))
    (directory/'report.json').write_text(json.dumps(report));return directory


@pytest.mark.parametrize('compressed',(False,True))
def test_bound_raw_logs_complete_analysis_without_calibrated_channels(tmp_path,compressed):
    m=tool();run=fixture_run(tmp_path/'run',compressed);result=m.analyze_run(run)
    assert result['shape']['zero_lag']['gain_px_per_counted_m']==pytest.approx(1000,rel=.005)
    assert result['apparent_return_offset_px']==0 and result['counted_return_offset_m']==0
    report=json.loads((run/'report.json').read_text());report['camera']['sha256']='0'*64
    (run/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='hash'):m.analyze_run(run)


def test_json_cli_is_immutable_and_requires_same_host_assertion(tmp_path):
    m=tool();run=fixture_run(tmp_path/'run');out=tmp_path/'analysis'
    with pytest.raises(SystemExit):m.main(['--run',str(run),'--output',str(out),'--no-plot'])
    assert not out.exists()
    args=['--run',str(run),'--output',str(out),'--no-plot','--same-host-clocks'];m.main(args)
    raw=(out/'analysis.json').read_bytes();result=json.loads(raw)
    assert result['independent_metric_scale'] is False and result['calibrated_latency'] is False
    with pytest.raises(SystemExit):m.main(args)
    assert (out/'analysis.json').read_bytes()==raw
