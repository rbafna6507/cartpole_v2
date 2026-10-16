import socket
from cartpole_vision.http import StreamingRequestHandler, ViewServer
from werkzeug.serving import ThreadedWSGIServer


def test_tailnet_mss_is_applied_before_listener_bind(monkeypatch):
    calls=[]
    class Socket:
        def setsockopt(self,*args):calls.append(args)
    server=object.__new__(ViewServer)
    server.socket=Socket();server.tcp_mss=1000
    monkeypatch.setattr(ThreadedWSGIServer,'server_bind',lambda self:calls.append('bind'))
    server.server_bind()
    assert calls==[(socket.IPPROTO_TCP,socket.TCP_MAXSEG,1000),'bind']


def test_stream_handler_disables_nagle_for_small_chunked_frames():
    assert StreamingRequestHandler.disable_nagle_algorithm is True


def test_view_mss_argument_is_bounded():
    import pytest
    from cartpole_vision.live import arguments
    assert arguments(['--view-tcp-mss','1000']).view_tcp_mss==1000
    for value in ('1','535','1221','9000'):
        with pytest.raises(SystemExit):arguments(['--view-tcp-mss',value])
