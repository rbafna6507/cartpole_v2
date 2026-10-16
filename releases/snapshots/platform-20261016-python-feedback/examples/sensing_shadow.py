#!/usr/bin/env python3
"""Read-only SDK shadow observer; persistent sensing stream or deterministic JSONL replay.

No Rig object, serial transport, arm operation or policy source selection exists
in this example. See docs/sensing.md for mandatory calibration/clock configuration.
"""
import argparse
import gzip
import math
from pathlib import Path
from urllib.parse import urlencode
import socket
import time
from cartpole_sdk.recording import strict_json_loads, canonical_json
from cartpole_sdk.sensing.shadow import ShadowObserver
from cartpole_sdk.sensing.vision import VisionHTTPClient
from cartpole_sdk.sensing.stream import SensingStreamClient, StreamDeadline


def replay(observer, source, output):
    for line in source:
        row=strict_json_loads(line)
        kind=row.get('type')
        if kind not in ('encoder','vision','encoder_batch','vision_queued','pending_flush'):continue
        now=row['received_ns']
        if kind=='encoder':observer.encoder(row['packet'],received_ns=now)
        elif kind=='encoder_batch':observer.encoder_batch(row['response'],received_ns=now)
        elif kind=='vision_queued':observer.enqueue_vision(row['snapshot'],received_ns=row.get('source_received_ns',now))
        elif kind=='pending_flush':observer.flush_pending(now_ns=now)
        else:observer.vision(row['snapshot'],received_ns=now)
        output.write(canonical_json(dict(type='shadow',packet=observer.packet(now_ns=now)))+'\n')


def read_cycle(observer, vision, encoder_url, *, record, client_factory=VisionHTTPClient,
               clock=time.monotonic_ns):
    """Camera first, then dense incremental serial history, then causal correction."""
    try:snapshot=vision.fetch()
    except (OSError,ValueError) as exc:
        record(dict(type='read_error',source='vision',reason=str(exc),received_ns=clock()))
    else:
        received=clock()
        record(dict(type='vision_queued',received_ns=received,snapshot=snapshot))
        observer.enqueue_vision(snapshot,received_ns=received)
    query={}
    if observer.last_encoder_sequence is not None:
        query=dict(after_seq=observer.last_encoder_sequence,session=observer.encoder_session)
    url=encoder_url+('?' + urlencode(query) if query else '')
    try:response=client_factory(url,timeout_s=.2,max_bytes=4_000_000).fetch()
    except (OSError,ValueError) as exc:
        record(dict(type='read_error',source='encoder',reason=str(exc),received_ns=clock()))
    else:
        received=clock()
        record(dict(type='encoder_batch',received_ns=received,response=response))
        observer.encoder_batch(response,received_ns=received)
    now=clock()
    record(dict(type='pending_flush',received_ns=now))
    observer.flush_pending(now_ns=now)



def consume_envelope(observer, envelope, *, received_ns, record, clock=time.monotonic_ns):
    """Preserve camera client receipt and source times; defer correction causally."""
    snapshot=envelope['vision']
    record(dict(type='vision_queued',received_ns=clock(),source_received_ns=received_ns,snapshot=snapshot))
    observer.enqueue_vision(snapshot,received_ns=received_ns)
    response=envelope['encoder']
    available=clock()
    record(dict(type='encoder_batch',received_ns=available,transport_received_ns=received_ns,response=response))
    observer.encoder_batch(response,received_ns=available)
    now=clock()
    record(dict(type='pending_flush',received_ns=now))
    observer.flush_pending(now_ns=now)


def run_stream(observer, client, *, deadline, max_hz, record, emit,
               clock=time.monotonic, clock_ns=time.monotonic_ns, sleep=time.sleep):
    """Reconnect only transport failures, without resetting source identity/maps."""
    consecutive_failures=0
    finished=False
    while clock()<deadline and not finished:
        messages=client.messages(deadline=deadline,max_hz=max_hz,
            after_seq=observer.last_encoder_sequence,session=observer.encoder_session)
        failure=None
        try:
            while True:
                try:
                    envelope,received=next(messages)
                except StreamDeadline:
                    finished=True
                    break
                except (OSError,StopIteration) as exc:
                    failure=exc
                    break
                consecutive_failures=0
                consume_envelope(observer,envelope,received_ns=received,record=record,clock=clock_ns)
                emit(clock_ns())
        finally:
            messages.close()
        if failure is not None:
            consecutive_failures+=1
            now=clock_ns()
            record(dict(type='read_error',source='sensing_stream',reason=str(failure) or 'stream ended',received_ns=now,
                        reconnect_attempt=consecutive_failures))
            # Retry only transport iteration failures. Disk/output errors must
            # propagate. Outage expiry stays replayable without reanchoring.
            record(dict(type='pending_flush',received_ns=now))
            observer.flush_pending(now_ns=now)
            emit(now)
            remaining=deadline-clock()
            if remaining>0:
                sleep(min(remaining,.05*min(consecutive_failures,4)))
    # Make expiry at the run deadline reviewable even if no final heartbeat arrived.
    now=clock_ns()
    record(dict(type='pending_flush',received_ns=now))
    observer.flush_pending(now_ns=now)
    emit(now)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,help='explicit source, upright anchor and clock JSON')
    parser.add_argument('--output',required=True,help='new JSONL capture/trace file; existing files are preserved')
    parser.add_argument('--replay',help='replay encoder/vision rows from a recorded shadow capture')
    parser.add_argument('--base-url',default='http://127.0.0.1:3090')
    parser.add_argument('--transport',choices=('stream','http'),default='stream',help='persistent stream (default) or legacy polling baseline')
    parser.add_argument('--duration',type=float,default=60.)
    parser.add_argument('--poll-hz',type=float,default=100.)
    parser.add_argument('--publish-port',type=int,default=3097,help='loopback actual SDK shadow stream; 0 disables; replay never publishes')
    args=parser.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration<=0:parser.error('positive finite duration required')
    if not math.isfinite(args.poll_hz) or not 1<=args.poll_hz<=200:parser.error('poll rate must be 1..200Hz')
    if args.transport=='stream' and (not args.poll_hz.is_integer() or not 10<=args.poll_hz<=100):
        parser.error('stream rate must be an integer 10..100Hz')
    if not 0<=args.publish_port<=65535:parser.error('publish port must be 0..65535')
    config=strict_json_loads(Path(args.config).read_text())
    observer=ShadowObserver(config)
    output_path=Path(args.output);output_path.parent.mkdir(parents=True,exist_ok=True)
    with output_path.open('x',encoding='utf-8') as output:
        output.write(canonical_json(dict(type='configuration',config=config,transport=args.transport))+'\n')
        if args.replay:
            opener=gzip.open if str(args.replay).endswith('.gz') else open
            with opener(args.replay,'rt') as source:replay(observer,source,output)
            return 0
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM) if args.publish_port else None
        if udp:udp.setblocking(False)
        deadline=time.monotonic()+args.duration
        def emit(now):
            packet=observer.packet(now_ns=now)
            output.write(canonical_json(dict(type='shadow',packet=packet))+'\n')
            if udp:
                try:udp.sendto(canonical_json(packet).encode(),('127.0.0.1',args.publish_port))
                except OSError:pass
        def record(row):output.write(canonical_json(row)+'\n')
        try:
            if args.transport=='stream':
                client=SensingStreamClient(args.base_url.rstrip('/')+'/api/sensing-stream')
                run_stream(observer,client,deadline=deadline,max_hz=int(args.poll_hz),record=record,emit=emit)
                return 0
            vision=VisionHTTPClient(args.base_url.rstrip('/')+'/api/state?measurement=1',timeout_s=.2)
            encoder_url=args.base_url.rstrip('/')+'/api/encoder'
            while time.monotonic()<deadline:
                start=time.monotonic()
                read_cycle(observer,vision,encoder_url,
                    record=record)
                emit(time.monotonic_ns());output.flush()
                time.sleep(max(0,1/args.poll_hz-(time.monotonic()-start)))
        except ValueError as exc:
            record(dict(type='fatal_error',source=args.transport,reason=str(exc),received_ns=time.monotonic_ns()))
            emit(time.monotonic_ns())
            raise
        finally:
            if udp:udp.close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
