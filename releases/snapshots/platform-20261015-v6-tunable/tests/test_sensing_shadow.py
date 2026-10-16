from dataclasses import asdict
import copy
import pytest
from cartpole_sdk.sensing.shadow import ShadowObserver
from cartpole_sdk.sensing.vision import calibration_fingerprint
from cartpole_sdk.sensing.telemetry import encoder_packet
from test_sensing_telemetry import state, info
from dataclasses import replace


def configuration():
    calibration={'home_angle_rad':0.,'home_length_px':100.}
    reference={'upright_raw':370,'firmware':'executor-v4-rehome'}
    def anchor(source,source_calibration_id):
        return dict(source=source,source_id=source+'-physical-a',source_frame_id='encoder-zero' if source=='magnetic' else 'camera-native',
            source_calibration_id=source_calibration_id,target_frame_id='upright-a',reference_id='held-direct-upright-a',zero_rad=0.,sign=1)
    return dict(schema_version=1,session_id='shadow-a',clock_id='local-monotonic',
        encoder_reference=reference,encoder_alignment=anchor('magnetic',calibration_fingerprint(reference)),
        vision_calibration=calibration,vision_alignment=anchor('vision',calibration_fingerprint(calibration)),
        encoder_clock=dict(strategy='receipt-anchor',receipt_delay_ns=0,uncertainty_ns=10_000_000,
            max_receipt_residual_ns=30_000_000,valid_for_ns=10_000_000_000),
        vision_clock=dict(source_clock_id='camera-host',session_clock_id='local-monotonic',offset_ns=0),
        fusion=dict(max_encoder_age_ns=100_000_000,max_vision_age_ns=200_000_000))


def snapshot(t=1.):
    return dict(t=t,theta_rad=.2,angle_valid=True,calibrated=True,calibration=configuration()['vision_calibration'])


def packet():return encoder_packet(state(),info(),sequence=1,generation=0)


def test_shadow_requires_explicit_calibration_and_mapping_then_emits_real_observation():
    config=configuration();s=ShadowObserver(config)
    assert s.encoder(packet(),received_ns=1_005_000_000)
    assert s.vision(snapshot(),received_ns=1_005_000_000)
    result=s.packet(now_ns=1_005_000_000)
    assert result['schema']=='cartpole-sdk-shadow-v1'
    assert result['control_eligible'] is False
    assert result['observation']['samples'][-1]['source']=='fused'
    assert result['observation']['samples'][-1]['validity']=='valid'
    assert result['diagnostics']['encoder_clock']['offset_ns']==980_000_000
    assert result['diagnostics']['encoder_clock']['uncertainty_ns']==10_000_000


def test_reference_change_and_board_session_change_invalidate_existing_observer():
    for field in ('upright','session','calibration'):
        s=ShadowObserver(configuration());s.encoder(packet(),received_ns=1_005_000_000)
        changed=packet();changed['seq']=2
        if field=='upright':changed['sdk_info']['encoder_upright_raw']=371
        if field=='session':changed['board_clock_id']='teensy:456'
        if field=='calibration':changed['sdk_state']['flags']|=256
        if field=='calibration':
            assert not s.encoder(changed,received_ns=1_006_000_000)
        else:
            with pytest.raises(ValueError):s.encoder(changed,received_ns=1_006_000_000)
        assert s.packet(now_ns=1_006_000_000)['observation']['samples'][-1]['validity']=='invalid'


def test_repeated_http_snapshots_do_not_update_fusion_twice():
    s=ShadowObserver(configuration());s.encoder(packet(),received_ns=1_005_000_000)
    s.vision(snapshot(),received_ns=1_005_000_000)
    assert not s.encoder(packet(),received_ns=1_010_000_000)
    assert not s.vision(snapshot(),received_ns=1_010_000_000)
    assert s.packet(now_ns=1_010_000_000)['diagnostics']['accepted_vision']==1


def test_unknown_clock_strategy_or_missing_camera_anchor_rejected():
    config=configuration();config['encoder_clock']['strategy']='guess'
    with pytest.raises(ValueError):ShadowObserver(config)
    config=configuration();del config['vision_alignment']['reference_id']
    with pytest.raises((ValueError,TypeError)):ShadowObserver(config)


def test_camera_calibration_change_is_detected_even_at_repeated_timestamp():
    s=ShadowObserver(configuration());s.encoder(packet(),received_ns=1_005_000_000)
    s.vision(snapshot(),received_ns=1_005_000_000)
    changed=snapshot();changed['calibration']['home_angle_rad']=.1
    with pytest.raises(ValueError,match='calibration'):
        s.vision(changed,received_ns=1_010_000_000)
    assert s.packet(now_ns=1_010_000_000)['diagnostics']['status']=='reset_required'


def test_shared_frame_label_does_not_replace_common_physical_reference():
    config=configuration();config['vision_alignment']['reference_id']='different-physical-anchor'
    with pytest.raises(ValueError,match='reference'):
        ShadowObserver(config)


def test_losing_info_after_alignment_invalidates_fusion_instead_of_retaining_reference():
    s=ShadowObserver(configuration())
    missing=packet();missing['sdk_info']=None
    assert not s.encoder(missing,received_ns=1_005_000_000)
    assert s.packet(now_ns=1_005_000_000)['diagnostics']['status']=='unavailable'
    s.encoder(packet(),received_ns=1_006_000_000)
    missing['seq']=2
    with pytest.raises(ValueError,match='INFO'):
        s.encoder(missing,received_ns=1_007_000_000)
    assert s.packet(now_ns=1_007_000_000)['observation']['samples'][-1]['validity']=='invalid'


def timed_packet(ms,seq):
    st=replace(state(),unwrapped_us=20_000+ms*1000,received_ns=1_000_000_000+ms*1_000_000,
               theta=.1+ms*.001)
    return encoder_packet(st,info(),sequence=seq,generation=0)


def test_dense_encoder_batch_survives_slow_http_poll_without_relaxing_gap_limit():
    config=configuration();config['encoder_clock']['receipt_delay_ns']=22_000_000
    s=ShadowObserver(config)
    # HTTP polling every 60 ms cannot itself satisfy the unchanged 30 ms gap gate.
    # The packet history contains the real 5 ms serial cadence.
    assert s.enqueue_vision(snapshot(1.025),received_ns=1_055_000_000)
    batch={'packets':[timed_packet(ms,seq) for seq,ms in enumerate(range(0,61,5),1)]}
    assert s.encoder_batch(batch,received_ns=1_060_000_000)==13
    assert s.flush_pending(now_ns=1_060_000_000)==1
    out=s.packet(now_ns=1_060_000_000)
    assert out['observation']['samples'][-1]['validity']=='valid'
    assert out['diagnostics']['accepted_vision']==1
    assert out['diagnostics']['last_vision_received_ns']==1_055_000_000
    assert out['diagnostics']['last_vision_available_ns']==1_060_000_000
    assert s.fusion.config.max_interpolation_gap_ns==30_000_000
    vision=next(x for x in out['observation']['samples'] if x['source']=='vision')
    assert vision['received_ns']==1_055_000_000  # Actual camera HTTP receipt retained.
    assert out['observation']['available_ns']==1_060_000_000
    assert s.fusion.history[0].received_ns==1_000_000_000  # Original serial receipt.


def test_future_camera_waits_boundedly_for_real_bracket_and_then_accepts():
    config=configuration();config['encoder_clock']['receipt_delay_ns']=22_000_000
    s=ShadowObserver(config)
    s.encoder_batch({'packets':[timed_packet(ms,seq) for seq,ms in enumerate(range(0,41,5),1)]},received_ns=1_040_000_000)
    s.enqueue_vision(snapshot(1.030),received_ns=1_045_000_000)
    assert s.flush_pending(now_ns=1_045_000_000)==0
    out=s.packet(now_ns=1_045_000_000)
    assert out['diagnostics']['pending_vision']==1
    assert out['observation']['samples'][-1]['validity']=='invalid'
    s.encoder_batch({'packets':[timed_packet(45,10),timed_packet(50,11),timed_packet(55,12)]},received_ns=1_060_000_000)
    assert s.flush_pending(now_ns=1_060_000_000)==1
    assert s.packet(now_ns=1_060_000_000)['diagnostics']['pending_vision']==0


def test_true_encoder_gap_remains_rejected_even_with_history_endpoint():
    s=ShadowObserver(configuration())
    s.enqueue_vision(snapshot(1.025),received_ns=1_055_000_000)
    s.encoder_batch({'packets':[timed_packet(0,1),timed_packet(60,2)]},received_ns=1_060_000_000)
    assert s.flush_pending(now_ns=1_060_000_000)==0
    assert s.fusion.diagnostics['rejected_vision']==1
    assert 'gap' in s.fusion.diagnostics['reason']


def test_pending_camera_expiry_and_capacity_never_become_unbounded_or_extrapolate():
    s=ShadowObserver(configuration())
    s.encoder(packet(),received_ns=1_005_000_000)
    for n in range(40):s.enqueue_vision(snapshot(1.01+n*.001),received_ns=1_060_000_000)
    assert s.flush_pending(now_ns=1_060_000_000)==0
    out=s.packet(now_ns=1_060_000_000)
    assert out['diagnostics']['pending_vision']==32
    assert out['diagnostics']['pending_vision_dropped']==8
    assert s.flush_pending(now_ns=1_500_000_000)==0
    out=s.packet(now_ns=1_500_000_000)
    assert out['diagnostics']['pending_vision']==0
    assert out['observation']['samples'][-1]['validity']=='invalid'


def test_delayed_history_ingest_keeps_old_samples_for_alignment_but_not_fresh_output():
    s=ShadowObserver(configuration())
    s.encoder_batch({'packets':[timed_packet(ms,seq) for seq,ms in enumerate(range(0,121,5),1)]},received_ns=1_150_000_000)
    assert len(s.fusion.history)==25
    out=s.packet(now_ns=1_250_000_000)
    assert out['observation']['samples'][-1]['validity']=='invalid'
    assert out['observation']['samples'][0]['validity']=='invalid'


def test_monitor_reads_camera_then_incremental_history_and_replays_deferred_receipts():
    import importlib.util
    import io,json
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('sensing_shadow_example',Path(__file__).parents[1]/'examples/sensing_shadow.py')
    example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
    config=configuration();config['encoder_clock']['receipt_delay_ns']=22_000_000
    observer=ShadowObserver(config);events=[];rows=[];call_times=iter([1_055_000_000,1_060_000_000,1_061_000_000])
    class Vision:
        def fetch(self):events.append('vision');return snapshot(1.025)
    class Encoder:
        def fetch(self):
            events.append('encoder')
            return {'packets':[timed_packet(ms,seq) for seq,ms in enumerate(range(0,61,5),1)]}
    urls=[]
    def factory(url,**kwargs):urls.append(url);return Encoder()
    example.read_cycle(observer,Vision(),'http://localhost/api/encoder',record=rows.append,
                       client_factory=factory,clock=lambda:next(call_times))
    assert events==['vision','encoder']
    assert observer.fusion.diagnostics['accepted_vision']==1
    replayed=ShadowObserver(config);output=io.StringIO()
    example.replay(replayed,io.StringIO('\n'.join(json.dumps(row) for row in rows)),output)
    assert replayed.fusion.diagnostics['accepted_vision']==1
    assert replayed.fusion.bias==observer.fusion.bias
    class EmptyEncoder:
        def fetch(self):return {'packets':[]}
    def empty_factory(url,**kwargs):urls.append(url);return EmptyEncoder()
    example.read_cycle(observer,Vision(),'http://localhost/api/encoder',record=rows.append,
                       client_factory=empty_factory,clock=lambda:1_070_000_000)
    assert urls[-1].endswith('?after_seq=13&session=123')


def test_live_example_selects_maintained_measurement_endpoint_before_any_request(monkeypatch,tmp_path):
    import importlib.util,json
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('sensing_shadow_endpoint',Path(__file__).parents[1]/'examples/sensing_shadow.py')
    example=importlib.util.module_from_spec(spec);spec.loader.exec_module(example)
    config=tmp_path/'config.json';config.write_text(json.dumps(configuration()))
    class EndProbe(Exception):pass
    def probe(observer,vision,encoder_url,**kwargs):
        assert vision.url=='http://localhost:3090/api/state?measurement=1'
        assert encoder_url=='http://localhost:3090/api/encoder'
        raise EndProbe()
    monkeypatch.setattr(example,'read_cycle',probe)
    with pytest.raises(EndProbe):
        example.main(['--config',str(config),'--output',str(tmp_path/'output.jsonl'),
                      '--base-url','http://localhost:3090/','--publish-port','0','--transport','http'])
