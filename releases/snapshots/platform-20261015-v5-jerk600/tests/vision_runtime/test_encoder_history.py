import time
from cartpole_vision.encoder_feed import Comparison
from cartpole_vision.app import Engine,create_app


def packet(seq,t,session='one',valid=True):
    return dict(v=1,session=session,seq=seq,host_t=t,board_ms=seq*4,theta=.1,theta_dot=0.,upright=370,generation=0,valid=valid,health={'status':'ok','age_s':0.},sdk_state={'seq':seq})


def test_encoder_batches_preserve_invalid_samples_and_cursor():
    comparison=Comparison()
    for seq in range(1,11):comparison.encoder(packet(seq,10+seq*.004,valid=seq!=5),now=10+seq*.004)
    result=comparison.packet(now=10.1,after_seq=3,session='one')
    assert [p['seq'] for p in result['packets']]==list(range(4,11))
    assert result['packets'][1]['valid'] is False
    assert result['latest_seq']==10 and result['oldest_seq']==1
    assert not result['history_truncated'] and not result['reset']
    comparison.encoder(packet(0,10.2,session='two'),now=10.2)
    result=comparison.packet(now=10.2,after_seq=10,session='one')
    assert result['reset'] and len(result['packets'])==1


def test_encoder_history_is_bounded_and_reports_lost_cursor():
    comparison=Comparison()
    now=time.monotonic()
    for seq in range(2500):comparison.encoder(packet(seq,now-10+seq*.004),now=now-10+seq*.004)
    result=comparison.packet(now=now,after_seq=0,session='one')
    assert len(result['packets'])<=1251
    assert result['history_truncated']
    client=create_app(Engine(comparison=comparison)).test_client()
    result=client.get('/api/encoder?after_seq=2495&session=one').json
    assert [p['seq'] for p in result['packets']]==[2496,2497,2498,2499]
