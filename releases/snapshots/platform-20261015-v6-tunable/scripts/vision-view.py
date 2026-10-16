#!/usr/bin/env python3
"""Localhost viewing proxy over the private Tailscale network.

WebCodecs requires a secure context (localhost qualifies). One independent TCP
connection per HTTP request avoids multiplexing video and telemetry over SSH.
The remote listener is view-only and must bind the Jetson's exact tailnet IP.
"""
import argparse
import ipaddress
import select
import socket
import socketserver


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='100.126.59.18')
    p.add_argument('--remote-port',type=int,default=3091)
    p.add_argument('--port',type=int,default=13090)
    a=p.parse_args()
    if ipaddress.ip_address(a.host) not in ipaddress.ip_network('100.64.0.0/10'):
        p.error('host must be an explicit tailnet IPv4 address')
    if not all(1<=port<=65535 for port in (a.port,a.remote_port)):p.error('ports must be 1..65535')
    class Relay(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                with socket.create_connection((a.host,a.remote_port),timeout=10) as upstream:
                    self.request.settimeout(10)
                    peers={self.request:upstream,upstream:self.request}
                    while True:
                        readable,_,_=select.select(list(peers),[],[],30)
                        if not readable:return
                        for source in readable:
                            chunk=source.recv(65536)
                            if not chunk:return
                            peers[source].sendall(chunk)
            except OSError:pass
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address=True
        daemon_threads=True
    with Server(('127.0.0.1',a.port),Relay) as server:
        print(f'Private viewer: http://127.0.0.1:{a.port} (Ctrl-C stops forwarding)',flush=True)
        try:server.serve_forever(poll_interval=.25)
        except KeyboardInterrupt:pass


if __name__=='__main__':main()
