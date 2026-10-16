from cartpole_vision.app import Engine, create_app
from cartpole_vision import live
import pytest


def test_remote_view_blocks_calibration_and_preserves_reading():
    client=create_app(Engine(),read_only=True).test_client()
    assert client.get('/').status_code==200
    assert client.get('/api/state').status_code==200
    assert client.get('/api/access').json['read_only'] is True
    for endpoint in ('/api/reset','/api/home','/api/select','/api/comparison','/api/cart/a','/api/cart/b','/api/template'):
        assert client.post(endpoint,json={}).status_code==403
    assert client.post('/api/video-mode',json={'mode':'tracked'}).status_code!=403


def test_view_bind_accepts_only_explicit_tailnet_ipv4():
    assert live.arguments(['--view-bind','100.126.59.18']).view_bind=='100.126.59.18'
    for address in ('0.0.0.0','192.168.1.1','8.8.8.8','::','localhost'):
        with pytest.raises(SystemExit):live.arguments(['--view-bind',address])
