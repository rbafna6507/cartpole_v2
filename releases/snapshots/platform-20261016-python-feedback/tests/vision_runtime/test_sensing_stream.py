import json,time,threading
from cartpole_vision.app import Engine,create_app
from cartpole_vision.sensing_stream import encode_envelope


def source(engine,seq):
    with engine.lock:
        now=time.monotonic()
        engine.estimator.last_t=now
        engine.estimator.last_state=dict(seq=seq,t=now,theta_rad=.2,angle_valid=True,
                                        frame_width=960,frame_height=600,calibrated=True)
        engine.processed+=1
        engine.changed.notify_all()


def test_stream_preserves_source_and_per_connection_cursor_without_engine_lock():
    engine=Engine();source(engine,7);calls=[]
    def packet(**kwargs):
        assert not engine.lock._is_owned()
        calls.append(kwargs)
        return dict(packet={'seq':9,'host_t':1,'sdk_state':{'received_ns':123}},
                    packets=[{'seq':9,'host_t':1,'sdk_state':{'received_ns':123}}],
                    session='test',latest_seq=9,oldest_seq=9,reset=False,history_truncated=False)
    engine.comparison.packet=packet
    client=create_app(engine).test_client()
    response=client.get('/api/sensing-stream?after_seq=8&session=test',buffered=False,
                        headers={'Accept-Encoding':'gzip'})
    assert response.mimetype=='application/x-ndjson'
    assert 'Content-Encoding' not in response.headers
    assert 'Content-Length' not in response.headers
    iterator=iter(response.response);first=json.loads(next(iterator))
    assert first['schema']=='cartpole-sensing-stream-v1'
    assert first['vision']['seq']==7 and first['vision']['frame_width']==960
    assert first['encoder']['packets'][0]['sdk_state']['received_ns']==123
    source(engine,8);second=json.loads(next(iterator))
    assert second['stream_seq']==1 and second['vision']['seq']==8
    assert calls[0]==dict(after_seq=8,session='test')
    assert calls[1]==dict(after_seq=9,session='test')
    response.close()
    other=client.get('/api/sensing-stream',buffered=False);next(iter(other.response));other.close()
    assert calls[-1]==dict(after_seq=None,session=None)


def test_stalled_camera_emits_stale_heartbeat_and_releases_subscriber():
    engine=Engine();source(engine,1)
    response=create_app(engine).test_client().get('/api/sensing-stream',buffered=False)
    it=iter(response.response);next(it)
    with engine.lock:engine.estimator.last_t=time.monotonic()-1
    started=time.monotonic();heartbeat=json.loads(next(it))
    assert time.monotonic()-started<.5
    assert heartbeat['vision']['stale'] and not heartbeat['vision']['angle_valid']
    response.close()
    assert all(engine.sensing_slots.acquire(blocking=False) for _ in range(4))
    assert not engine.sensing_slots.acquire(blocking=False)


def test_stream_limits_subscribers_and_validates_queries():
    engine=Engine();client=create_app(engine).test_client()
    for query in ('max_hz=0','max_hz=101','max_hz=nan','after_seq=-1'):
        assert client.get('/api/sensing-stream?'+query).status_code==400
    responses=[client.get('/api/sensing-stream',buffered=False) for _ in range(4)]
    assert client.get('/api/sensing-stream').status_code==429
    for response in responses:response.close()
    response=client.get('/api/sensing-stream',buffered=False)
    assert response.status_code==200
    response.close()


def test_bounded_line_trims_old_history_explicitly_not_source_times():
    packets=[dict(seq=i,host_t=i/250,payload='x'*500) for i in range(12)]
    encoder=dict(packet=packets[-1],packets=packets,session='s',oldest_seq=0,
                 latest_seq=11,history_truncated=False)
    line=encode_envelope({'seq':3,'t':12.3},encoder,0,15,max_bytes=2400)
    assert len(line)<=2400 and line.endswith(b'\n')
    data=json.loads(line)
    assert data['encoder']['history_truncated']
    assert data['encoder']['packets'][-1]['seq']==11
    assert data['vision']['t']==12.3
    assert encoder['history_truncated'] is False


def test_stream_sets_only_connection_local_backpressure_bounds():
    import socket
    class Connection:
        def __init__(self):self.calls=[]
        def settimeout(self,value):self.calls.append(('timeout',value))
        def setsockopt(self,*args):self.calls.append(args)
    connection=Connection()
    response=create_app(Engine()).test_client().get('/api/sensing-stream',buffered=False,
                  environ_overrides={'werkzeug.socket':connection})
    assert (socket.SOL_SOCKET,socket.SO_SNDBUF,32768) in connection.calls
    assert ('timeout',5) in connection.calls
    response.close()
