import gzip,json
from cartpole_vision.app import Engine, create_app


def test_json_compression_preserves_source_contract():
    client=create_app(Engine()).test_client()
    plain=client.get('/api/state')
    packed=client.get('/api/state',headers={'Accept-Encoding':'gzip'})
    assert packed.headers.get('Content-Encoding')=='gzip'
    assert json.loads(gzip.decompress(packed.data))['calibration']==plain.json['calibration']
    assert len(packed.data)<len(plain.data)
    assert 'Accept-Encoding' in packed.headers['Vary']


def test_chart_bootstrap_limit_is_optional_and_does_not_drop_cursor():
    engine=Engine()
    for seq in range(200):engine.history.append(dict(seq=seq,t=seq/60,theta_rad=0))
    client=create_app(engine).test_client()
    full=client.get('/api/state?history=1').json['history']
    bounded=client.get('/api/state?history=1&history_limit=30').json['history']
    assert len(full['samples'])==200
    assert len(bounded['samples'])==30
    assert full['last_seq']==bounded['last_seq']==199


def test_measurement_only_fetch_does_not_wait_for_diagnostic_subsystems():
    engine=Engine()
    engine.estimator.last_t=10
    engine.estimator.last_state=dict(t=10,seq=7,theta_rad=.2,angle_valid=True,calibrated=True,
                                    frame_width=960,frame_height=600,host_read_to_result_ms=3.)
    def unavailable(*args,**kwargs):raise RuntimeError("diagnostic subsystem unavailable")
    engine.snapshot=unavailable
    response=create_app(engine).test_client().get('/api/state?measurement=1')
    assert response.status_code==200
    assert response.json['seq']==7 and response.json['frame_width']==960
    assert 'calibration' in response.json and 'comparison' not in response.json
