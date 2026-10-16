"""Offline CRC and decode/accept benchmark; no transport is constructed."""
import binascii,json,platform,statistics,time
from pathlib import Path
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig import protocol

original=protocol.crc16
def legacy(data):
 crc=0xffff
 for byte in data:
  crc^=byte<<8
  for _ in range(8):
   crc=((crc<<1)^(0x1021 if crc&0x8000 else 0))&0xffff
 return crc
fast=lambda data:binascii.crc_hqx(data,0xffff)
payload=b'V2 S 4221735329 83201215 1601354050 12 207 -2.883884 -2.796363 17.92482 0.1593375 -0.35 1.5 -3.40065982 683 0 0 18998842 0'
results={}
for label,fn in [('python',legacy),('binascii',fast)]:
 batches=[]
 for _ in range(5):
  started=time.perf_counter_ns()
  for i in range(10_000):fn(payload)
  batches.append((time.perf_counter_ns()-started)/10_000/1000)
 results[label]={'crc_us_per_call':batches,'crc_median_us':statistics.median(batches)}
frames=[]
for i in range(2000):
 p=f'V2 S 42 {i*4} {i*4000} 12 207 -2.883884 -2.796363 17.92482 0.1593375 -0.35 1.5 -3.40065982 683 0 0 18998842 0'
 frames.append(protocol.encode(p))
try:
 for label,fn in [('python',legacy),('binascii',fast)]:
  batches=[]
  protocol.crc16=fn
  for _ in range(5):
   rig=Rig('never-connected');rig._sid=42;rig._handshake=True
   started=time.perf_counter_ns()
   for frame in frames:rig._accept(protocol.decode(frame),time.monotonic_ns())
   batches.append((time.perf_counter_ns()-started)/len(frames)/1000)
  results[label].update(decode_accept_us_per_call=batches,decode_accept_median_us=statistics.median(batches))
finally:protocol.crc16=original
report=dict(platform=platform.platform(),frame_body_bytes=len(payload),results=results,
    note='Mac local timing; full decode + Rig._accept includes parse, condition lock, replace, history eviction, state asdict and record deque; logger/mirror threads disabled; no hardware')
Path('/tmp/cartpole-python-id-20261016/crc-benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
