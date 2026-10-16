"""Bounded persistent transport tests; no network or camera is opened."""
import importlib.util
import io
import json
from pathlib import Path
import pytest
from cartpole_sdk.sensing.stream import SensingStreamClient, StreamDeadline, StreamDisconnected
from cartpole_sdk.sensing.shadow import ShadowObserver
from test_sensing_shadow import configuration, snapshot, timed_packet


def envelope(vision=None, packets=()):
    return dict(schema='cartpole-sensing-stream-v1', stream_seq=1, host_t=1.,
                vision=snapshot() if vision is None else vision,
                encoder=dict(packets=list(packets)))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False)+'\n').encode()


class FakeResponse:
    status=200
    def __init__(self, chunks):self.chunks=iter(chunks);self.closed=False
    def getheader(self, name, default=None):return default
    def read1(self, size):
        value=next(self.chunks,b'')
        if isinstance(value,Exception):raise value
        assert len(value)<=size
        return value
    def close(self):self.closed=True


class FakeConnection:
    def __init__(self, response):self.response=response;self.closed=False;self.requests=[]
    def request(self, *args, **kwargs):self.requests.append((args,kwargs))
    def getresponse(self):return self.response
    def close(self):self.closed=True


def client_for(chunks, **kwargs):
    response=FakeResponse(chunks);connection=FakeConnection(response)
    client=SensingStreamClient('http://localhost:3090/api/sensing-stream',
        connection_factory=lambda *args,**kwargs:connection, **kwargs)
    return client,connection,response


def test_partial_lines_utf8_and_multiple_records_preserve_envelope_receipt_and_resume_cursor():
    row=envelope();row['label']='\N{GREEK SMALL LETTER THETA}'
    data=encoded(row);split=data.index(b'\xce')+1
    times=iter([1_010_000_000,1_020_000_000,1_030_000_000])
    client,conn,response=client_for([data[:split],data[split:],encoded(envelope())],
                                   clock=lambda:1.,clock_ns=lambda:next(times))
    received=[]
    with pytest.raises(StreamDisconnected):
        for record,now in client.messages(deadline=2.,after_seq=42,session=123,max_hz=100):
            received.append((record,now))
    assert [now for _,now in received]==[1_020_000_000,1_030_000_000]
    assert received[0][0]['label']=='θ'
    assert conn.requests[0][0]==('GET','/api/sensing-stream?max_hz=100&after_seq=42&session=123')
    assert conn.requests[0][1]['headers']['Accept-Encoding']=='identity'
    assert conn.closed and response.closed


def test_multiple_complete_records_in_one_read_have_same_receipt():
    client,_,_=client_for([encoded(envelope())*2],clock=lambda:1.,clock_ns=lambda:1_010_000_000)
    records=[]
    with pytest.raises(StreamDisconnected):
        records.extend(client.messages(deadline=2.))
    assert len(records)==2 and records[0][1]==records[1][1]


@pytest.mark.parametrize('wire,reason',[(b'x'*65,'limit'),(b'{bad}\n','JSON'),
    (encoded({'schema':'other'}),'schema'),(encoded(dict(envelope(),encoder={})), 'packets')])
def test_oversize_malformed_and_wrong_schema_are_fatal(wire,reason):
    client,conn,response=client_for([wire],max_line_bytes=64 if reason=='limit' else 1000,
                                    clock=lambda:1.)
    with pytest.raises(ValueError,match=reason):list(client.messages(deadline=2.))
    assert conn.closed and response.closed


def test_disconnect_with_partial_record_does_not_deliver_it():
    client,conn,response=client_for([encoded(envelope())[:-1]],clock=lambda:1.)
    with pytest.raises(StreamDisconnected,match='partial'):
        list(client.messages(deadline=2.))
    assert conn.closed and response.closed


def test_absolute_deadline_stops_partial_record_drip_and_closes_connection():
    now=[0.]
    client,conn,response=client_for([b'{']*100,clock=lambda:now[0])
    original=response.read1
    def read(size):now[0]+=.04;return original(size)
    response.read1=read
    with pytest.raises(StreamDeadline):list(client.messages(deadline=.1))
    assert now[0]==pytest.approx(.12)
    assert conn.closed and response.closed


def test_actual_http_chunked_parser_and_low_level_reads_share_absolute_deadline():
    from cartpole_sdk.sensing.stream import _DeadlineSocket
    import http.client
    data=encoded(envelope())
    wire=(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'+
          ('%x\r\n'%len(data)).encode()+data+b'\r\n0\r\n\r\n')
    class Socket:
        def __init__(self):self.raw=io.BytesIO(wire);self.timeouts=[]
        def makefile(self,*args,**kwargs):return self.raw
        def settimeout(self,value):self.timeouts.append(value)
    sock=Socket();now=[.9]
    response=http.client.HTTPResponse(_DeadlineSocket(sock,deadline=1.,timeout_s=.2,clock=lambda:now[0]))
    response.begin()
    assert json.loads(response.read1(4096))==envelope()
    assert max(sock.timeouts)==pytest.approx(.1)
    response.close()
    # Buffered chunk framing needs no socket read. The next raw read still
    # checks the same absolute deadline, including dripped HTTP headers.
    now[0]=1.
    reader=_DeadlineSocket(Socket(),deadline=1.,timeout_s=.2,clock=lambda:now[0]).makefile('rb')
    with pytest.raises(StreamDeadline):reader.read1(4096)
    reader.close()


def example_module():
    spec=importlib.util.spec_from_file_location('stream_example',Path(__file__).parents[1]/'examples/sensing_shadow.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_stream_dense_history_future_camera_heartbeat_and_replay_keep_receipts():
    example=example_module();config=configuration();config['encoder_clock']['receipt_delay_ns']=22_000_000
    observer=ShadowObserver(config);rows=[]
    first=envelope(snapshot(1.030),[timed_packet(ms,seq) for seq,ms in enumerate(range(0,41,5),1)])
    example.consume_envelope(observer,first,received_ns=1_045_000_000,record=rows.append,clock=lambda:1_046_000_000)
    assert observer.fusion.diagnostics['accepted_vision']==0
    assert len(observer.pending_vision)==1
    second=envelope(snapshot(1.030),[timed_packet(45,10),timed_packet(50,11),timed_packet(55,12)])
    example.consume_envelope(observer,second,received_ns=1_060_000_000,record=rows.append,clock=lambda:1_061_000_000)
    assert observer.fusion.diagnostics['accepted_vision']==1
    assert observer.fusion.diagnostics['last_vision_received_ns']==1_045_000_000
    assert observer.fusion.diagnostics['last_vision_available_ns']==1_061_000_000
    assert observer.fusion.history[0].received_ns==1_000_000_000
    assert observer.fusion.config.max_interpolation_gap_ns==30_000_000
    replayed=ShadowObserver(config)
    example.replay(replayed,io.StringIO('\n'.join(json.dumps(row) for row in rows)),io.StringIO())
    assert replayed.fusion.bias==observer.fusion.bias
    assert replayed.fusion.diagnostics['accepted_vision']==1
    assert observer.packet(now_ns=1_500_000_000)['observation']['samples'][-1]['validity']=='invalid'


def test_stream_reconnect_resumes_cursor_without_reanchoring_and_records_failure():
    example=example_module();observer=ShadowObserver(configuration());now=[1.005];rows=[];outputs=[];calls=[]
    first=envelope(snapshot(1.),[timed_packet(0,1)])
    class Client:
        def messages(self,**kwargs):
            calls.append(kwargs)
            if len(calls)==1:
                yield first,1_005_000_000
                raise StreamDisconnected('closed')
            now[0]=2.
            raise StreamDeadline('duration')
            yield
    def sleep(seconds):now[0]+=seconds
    example.run_stream(observer,Client(),deadline=2.,max_hz=100,record=rows.append,
                       emit=outputs.append,clock=lambda:now[0],clock_ns=lambda:round(now[0]*1e9),sleep=sleep)
    assert len(calls)==2
    assert calls[1]['after_seq']==1 and calls[1]['session']=='123'
    assert len([r for r in rows if r['type']=='read_error'])==1
    assert observer.fusion is not None and observer.error is None


def test_stream_source_identity_error_is_fatal_and_never_reconnects():
    example=example_module();observer=ShadowObserver(configuration());calls=[]
    changed=snapshot();changed['calibration']['home_angle_rad']=.1
    class Client:
        def messages(self,**kwargs):
            calls.append(kwargs);yield envelope(changed,[timed_packet(0,1)]),1_005_000_000
    with pytest.raises(ValueError,match='calibration'):
        example.run_stream(observer,Client(),deadline=2.,max_hz=100,record=lambda row:None,
                           emit=lambda now:None,clock=lambda:1.,clock_ns=lambda:1_005_000_000)
    assert len(calls)==1


def test_cli_defaults_to_stream(monkeypatch,tmp_path):
    example=example_module();path=tmp_path/'config.json';path.write_text(json.dumps(configuration()))
    calls=[]
    def run(observer,client,**kwargs):calls.append((client,kwargs))
    monkeypatch.setattr(example,'run_stream',run)
    assert example.main(['--config',str(path),'--output',str(tmp_path/'capture.jsonl'),'--publish-port','0'])==0
    assert calls[0][0].url=='http://127.0.0.1:3090/api/sensing-stream'
    assert calls[0][1]['max_hz']==100


def test_buffered_envelopes_have_shared_receipt_but_sequential_availability_and_replay():
    example=example_module();observer=ShadowObserver(configuration());rows=[];outputs=[]
    envelopes=[envelope(snapshot(1.005),[timed_packet(ms,seq) for seq,ms in enumerate(range(0,21,5),1)]),
               envelope(snapshot(1.030),[timed_packet(ms,seq) for seq,ms in enumerate(range(25,41,5),6)])]
    now=[1_045_000_000]
    def clock_ns():now[0]+=100_000;return now[0]
    class Client:
        def messages(self,**kwargs):
            for row in envelopes:yield row,1_045_000_000
            raise StreamDeadline('end')
    def emit(when):outputs.append(observer.packet(now_ns=when))
    example.run_stream(observer,Client(),deadline=2.,max_hz=100,record=rows.append,
                       emit=emit,clock=lambda:now[0]/1e9,clock_ns=clock_ns)
    assert observer.error is None
    assert observer.fusion.diagnostics['accepted_vision']==2
    assert observer.fusion.diagnostics['last_vision_received_ns']==1_045_000_000
    assert observer.fusion.diagnostics['last_vision_available_ns']>1_045_000_000
    assert [row['received_ns'] for row in rows]==sorted(row['received_ns'] for row in rows)
    replayed=ShadowObserver(configuration())
    example.replay(replayed,io.StringIO('\n'.join(json.dumps(row) for row in rows)),io.StringIO())
    assert replayed.error is None
    assert replayed.fusion.bias==observer.fusion.bias
    assert replayed.fusion.diagnostics['accepted_vision']==2


def test_output_failure_is_not_misclassified_as_transport_reconnect():
    example=example_module();observer=ShadowObserver(configuration());calls=[]
    class Client:
        def messages(self,**kwargs):
            calls.append(kwargs);yield envelope(snapshot(1.),[timed_packet(0,1)]),1_005_000_000
    def failed_write(row):raise OSError('disk full')
    with pytest.raises(OSError,match='disk full'):
        example.run_stream(observer,Client(),deadline=2.,max_hz=100,record=failed_write,
                           emit=lambda now:None,clock=lambda:1.,clock_ns=lambda:1_005_000_000)
    assert len(calls)==1


def test_startup_camera_unavailable_heartbeat_keeps_encoder_and_still_checks_calibration():
    example=example_module();observer=ShadowObserver(configuration());rows=[]
    missing=dict(calibration=configuration()['vision_calibration'],stale=True,angle_valid=False)
    example.consume_envelope(observer,envelope(missing,[timed_packet(0,1)]),received_ns=1_005_000_000,
                             record=rows.append,clock=lambda:1_006_000_000)
    assert observer.error is None and observer.last_encoder_sequence==1
    assert observer.packet(now_ns=1_006_000_000)['observation']['samples'][-1]['validity']=='invalid'
    replayed=ShadowObserver(configuration())
    example.replay(replayed,io.StringIO('\n'.join(json.dumps(row) for row in rows)),io.StringIO())
    assert replayed.error is None and replayed.last_encoder_sequence==1
    missing['calibration']['home_angle_rad']=.1
    with pytest.raises(ValueError,match='calibration'):
        example.consume_envelope(observer,envelope(missing),received_ns=1_010_000_000,
                                 record=rows.append,clock=lambda:1_011_000_000)


def test_http_header_drip_cannot_extend_absolute_run_deadline():
    from cartpole_sdk.sensing.stream import _DeadlineSocket
    import http.client
    now=[0.]
    class Drip(io.RawIOBase):
        def readinto(self,buffer):
            now[0]+=.01
            buffer[0]=ord('H')
            return 1
    class Socket:
        def makefile(self,*args,**kwargs):return Drip()
        def settimeout(self,value):assert 0<value<=.2
    response=http.client.HTTPResponse(_DeadlineSocket(Socket(),deadline=.08,timeout_s=.2,clock=lambda:now[0]))
    with pytest.raises(StreamDeadline):response.begin()
    assert now[0]==pytest.approx(.08)
    response.close()
