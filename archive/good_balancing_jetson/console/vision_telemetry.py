"""Best-effort loopback telemetry mirror. Never reads serial or sends rig commands."""
import json
import math
import socket
import time
import uuid

class Publisher:
    def __init__(self,port=3096):
        if not 0<=port<=65535:raise ValueError('invalid vision telemetry port')
        self.port=port;self.session=uuid.uuid4().hex;self.seq=0;self.generation=0
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM) if port else None
        if self.socket:self.socket.setblocking(False)
        self.dropped=0;self.last_health=None

    def reset(self):
        self.generation+=1;self.last_health=None

    def health(self,board_ms,valid,status,errors,now=None):
        self.last_health=dict(board_ms=board_ms,valid=bool(valid),magnet_status=status,
                              i2c_errors=errors,t=time.monotonic() if now is None else now)

    def publish(self,board_ms,theta,theta_dot,upright,now=None,valid=True):
        if self.socket is None:return
        now=time.monotonic() if now is None else now
        if not all(math.isfinite(v) for v in (board_ms,theta,theta_dot,now)):return
        self.seq+=1
        h=self.last_health
        age=None if h is None else now-h['t']
        health_status='unknown'
        if h is not None:
            health_status='ok' if h['valid'] and h['magnet_status'] & 32 and not h['magnet_status'] & 24 else 'invalid'
            if not 0<=age<=.25 or (board_ms-h['board_ms']) % (2**32)>250:health_status='stale'
        health=dict(status=health_status,age_s=age,period_s=.1,
                    magnet_status=None if h is None else h['magnet_status'],
                    i2c_errors=None if h is None else h['i2c_errors'])
        valid=bool(valid and health_status=='ok')
        packet=dict(v=1,session=self.session,seq=self.seq,board_ms=board_ms,host_t=now,
                    theta=theta,theta_dot=theta_dot,upright=upright,generation=self.generation,valid=bool(valid),health=health)
        try:self.socket.sendto(json.dumps(packet,allow_nan=False).encode(),('127.0.0.1',self.port))
        except (OSError,ValueError):self.dropped+=1

    def close(self):
        if self.socket:self.socket.close();self.socket=None
