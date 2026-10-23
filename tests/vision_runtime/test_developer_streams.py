import json
import time
from cartpole_vision.app import Engine, create_app
from .test_detector import scene


def test_catalog_marks_absent_sensor_native_streams():
    response = create_app(Engine()).test_client().get('/api/streams')
    assert response.status_code == 200
    catalog = {s['id']: s for s in response.json['streams']}
    assert catalog['encoder.native_counts']['status'] == 'unavailable'
    assert catalog['camera.sensor_raw']['status'] == 'unavailable'
    assert catalog['vision.raw']['delivery'] == 'latest_only'


def test_selected_stream_preserves_source_time_and_cursor_suppresses_duplicates():
    engine = Engine()
    t = time.monotonic()
    engine.process(scene(), t, 42)
    client = create_app(engine).test_client()
    response = client.get('/api/streams/ndjson?streams=vision.raw,vision.processed&duration=.01')
    assert response.status_code == 200
    rows = [json.loads(line) for line in response.data.splitlines()]
    assert rows[0]['channels']['vision.raw']['samples'][0]['t'] == t
    assert rows[0]['channels']['vision.processed']['samples'][0]['seq'] == 42
    assert set(rows[0]['channels']) == {'vision.raw', 'vision.processed'}
    resumed = client.get('/api/streams/ndjson', query_string={'streams':'vision.raw,vision.processed', 'duration':'.01', 'cursors':json.dumps(rows[0]['cursors'])})
    assert json.loads(resumed.data.splitlines()[0])['channels']['vision.raw']['samples'] == []


def test_invalid_selection_and_bounds_do_not_allocate_subscriber():
    client = create_app(Engine()).test_client()
    for query in ('streams=nope', 'streams=camera.sensor_raw', 'duration=nan', 'max_hz=1000', 'cursors=[]', 'limit=0'):
        assert client.get('/api/streams/ndjson?' + query).status_code == 400


def test_board_fields_preserved_and_history_limit_resumes():
    engine = Engine(); now = time.monotonic()
    for seq in range(3):
        engine.comparison.encoder(dict(v=1, session='test', seq=seq, generation=0,
            valid=True, host_t=now, board_ms=seq, theta=.1, theta_dot=.2,
            theta_raw=.12, governor={'clamped':True}, health={'status':'ok','age_s':0}), now)
    client = create_app(engine).test_client()
    first = json.loads(client.get('/api/streams/ndjson?streams=board.telemetry&limit=1&duration=.001').data)
    assert first['channels']['board.telemetry']['samples'][0]['theta_raw'] == .12
    assert first['channels']['board.telemetry']['samples'][0]['governor'] == {'clamped':True}
    second = json.loads(client.get('/api/streams/ndjson', query_string=dict(streams='board.telemetry', limit=1, duration=.001, cursors=json.dumps(first['cursors']))).data)
    assert second['channels']['board.telemetry']['samples'][0]['seq'] == 1


def test_collector_real_http_preserves_envelopes_and_bounds(tmp_path):
    import importlib.util
    assert importlib.util.find_spec('cartpole_sdk.sensing.collect') is not None
    from cartpole_sdk.sensing.collect import collect
    import threading
    from werkzeug.serving import make_server
    engine = Engine(); engine.process(scene(), time.monotonic(), 5)
    server = make_server('127.0.0.1', 0, create_app(engine), threaded=True)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    try:
        path = tmp_path / 'data.jsonl'
        with path.open('x') as output:
            count = collect(f'http://127.0.0.1:{server.server_port}', output, streams=['vision.raw'], duration=.1, max_records=1)
        assert count == 1
        assert json.loads(path.read_text())['channels']['vision.raw']['samples'][0]['seq'] == 5
    finally:
        server.shutdown(); thread.join(); server.server_close()


def test_sdk_original_packet_and_generation_reset_are_preserved():
    from cartpole_vision.sdk_feed import SDKFeed
    from .test_sdk_feed import packet
    engine = Engine(); engine.sdk = SDKFeed(None)
    original = packet(t=time.monotonic())
    assert engine.sdk.accept(original)
    client = create_app(engine).test_client()
    first = json.loads(client.get('/api/streams/ndjson?streams=sdk.shadow&duration=.001').data)
    assert first['channels']['sdk.shadow']['samples'] == [original]
    updated = packet(seq=2, t=time.monotonic()); updated['diagnostics']['calibration_id'] = 'new'
    assert engine.sdk.accept(updated)
    second = json.loads(client.get('/api/streams/ndjson', query_string=dict(streams='sdk.shadow', duration=.001, cursors=json.dumps(first['cursors']))).data)
    assert second['channels']['sdk.shadow']['reset'] is True
    assert second['channels']['sdk.shadow']['samples'] == [updated]


def test_legacy_collector_real_http_preserves_v1(tmp_path):
    from cartpole_sdk.sensing.collect import collect
    import threading
    from werkzeug.serving import make_server
    engine = Engine(); engine.process(scene(), time.monotonic(), 19)
    server = make_server('127.0.0.1', 0, create_app(engine), threaded=True)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    try:
        path = tmp_path / 'legacy.jsonl'
        with path.open('x') as output:
            assert collect(f'http://127.0.0.1:{server.server_port}', output, legacy_sensing=True, duration=1, max_records=1) == 1
        data = json.loads(path.read_text())
        assert data['schema'] == 'cartpole-sensing-stream-v1'
        assert data['vision']['seq'] == 19
    finally:
        server.shutdown(); thread.join(); server.server_close()


def test_board_generation_change_resets_cursor_even_same_session():
    engine = Engine(); client = create_app(engine).test_client(); now = time.monotonic()
    packet = dict(v=1, session='same', seq=1, generation=0, valid=True,
                  host_t=now, board_ms=1, theta=.1, theta_dot=.2,
                  health={'status':'ok','age_s':0})
    engine.comparison.encoder(packet, now)
    first = json.loads(client.get('/api/streams/ndjson?streams=board.telemetry&duration=.001').data)
    engine.comparison.encoder(dict(packet, seq=2, generation=1), now)
    second = json.loads(client.get('/api/streams/ndjson', query_string=dict(streams='board.telemetry', duration=.001, cursors=json.dumps(first['cursors']))).data)
    assert second['channels']['board.telemetry']['reset'] is True


def test_cli_empty_deadline_is_reported_as_no_data(capsys):
    from cartpole_sdk.sensing.collect import main
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); time.sleep(.2)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    try:
        assert main(['--url', f'http://127.0.0.1:{server.server_port}', '--duration', '.05']) == 1
        assert 'no complete records' in capsys.readouterr().err
    finally:
        server.shutdown(); thread.join(); server.server_close()


def test_diagnostic_counts_catalog_keeps_diagnostic_provenance():
    engine = Engine(); now = time.monotonic()
    engine.comparison.encoder(dict(v=1, session='test', seq=1, generation=0,
        valid=True, host_t=now, board_ms=1, theta=.1, theta_dot=.2,
        sdk_info={'encoder_raw':123}, health={'status':'ok','age_s':0,'diagnostic_received_ns':1234}), now)
    catalog = create_app(engine).test_client().get('/api/streams').json
    diagnostic = next(s for s in catalog['streams'] if s['id'] == 'encoder.native_counts_diagnostic')
    assert diagnostic['status'] == 'available'
    assert diagnostic['source_channel'] == 'board.telemetry'
    assert diagnostic['timestamp_field'] == 'health.diagnostic_received_ns'


def test_stale_vision_has_explicit_freshness_without_rewriting_original_sample():
    from cartpole_vision.developer_streams import snapshot
    engine=Engine()
    original={'seq':1,'t':time.monotonic()-60,'angle_valid':True,'theta_rad':.1}
    engine.estimator.last_state=dict(original)
    result=snapshot(engine,('vision.processed',),{},128)['channels']['vision.processed']
    assert result['status']=='stale'
    assert result['age_s']>=60
    assert result['samples']==[original]


def test_comparison_discontinuity_is_not_claimed_as_missing_samples():
    from cartpole_vision.developer_streams import snapshot
    engine=Engine()
    class Comparison:
        def snapshot(self,**kwargs):
            return {'epoch':'same','status':{'source':'stale','encoder_health':{'status':'stale','age_s':1}},'encoder':{'samples':[{'seq':3,'t':1,'theta_rad':.2}]},'fused':{'samples':[]}}
    engine.comparison=Comparison()
    result=snapshot(engine,('comparison.encoder',),{'comparison.encoder':{'identity':'same','seq':1}},128)['channels']['comparison.encoder']
    assert result['gap'] is None
    assert result['sequence_discontinuity'] is True
    assert result['status']=='stale'
    assert result['producer_status']['encoder_health']['age_s']==1
