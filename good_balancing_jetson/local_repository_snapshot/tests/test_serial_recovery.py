import binascii
import importlib.util
import json
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('console_recovery',ROOT/'cartpole.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

def frame(payload):
    data=payload.encode('ascii')
    return b'@'+data+b'*'+f'{binascii.crc_hqx(data,0xffff):04X}\n'.encode()

class Serial:
    def __init__(self):self.lines=queue.Queue();self.commands=[];self.closed=False
    @property
    def in_waiting(self):return 1024
    def read(self,size):
        try:
            v=self.lines.get(timeout=.01)
            if isinstance(v,Exception):raise v
            return v
        except queue.Empty:return b''
    def write(self,data):self.commands.append(data)
    def close(self):self.closed=True

def until(predicate):
    deadline=time.monotonic()+4
    while not predicate() and time.monotonic()<deadline:time.sleep(.01)
    assert predicate(), 'timed out'

def ready(serial):
    serial.lines.put(frame('# STOP')+b''.join(frame(f'T {100+i*40} 0 0 0 0 0 0 -1 0 0 90 500') for i in range(3)))

class RecoveryTest(unittest.TestCase):
    def test_partial_and_combined_checked_lines_preserved(self):
        s=Serial()
        with tempfile.TemporaryDirectory() as d,patch.object(C.serial,'Serial',return_value=s):
            link=C.Link('fake',logdir=d,verbose=False)
            try:
                data=frame('= jmax 60')+frame('T 100 2 0 0 0 0 0 -1 0 0 90 500')+frame('E 100 4095 3 80 32 0 1 0')
                for block in [data[:7],data[7:27],data[27:]]:s.lines.put(block)
                until(lambda:link.encoder_sequence==1)
                self.assertEqual(link.params['jmax'],60);self.assertEqual(link.rx_count,1)
                self.assertEqual(link.encoder_samples[-1]['raw'],4095)
                self.assertEqual(link.bad_frames,0)
            finally:link.close()
    def test_disconnect_reconnect_stops_and_never_replays_auto(self):
        first,second=Serial(),Serial()
        with tempfile.TemporaryDirectory() as d,patch.object(C.serial,'Serial',side_effect=[first,second]) as factory:
            link=C.Link('fake',logdir=d,verbose=False)
            try:
                ready(first);until(lambda:not link._motion_block_reason())
                self.assertTrue(link.send('auto'))
                first.lines.put(OSError('Device not configured'))
                until(lambda:link.recovering)
                self.assertFalse(link.send('auto'))
                until(lambda:b'params\n' in second.commands)
                self.assertNotIn(b'auto\n',second.commands)
                self.assertEqual(second.commands[0],b'stop\n')
                self.assertTrue(link.recovering)
                ready(second)
                until(lambda:link.rx_count==6 and not link.recovering)
                self.assertIsNone(link.rx_error)
                self.assertTrue(factory.call_args.kwargs['exclusive'])
                self.assertEqual(factory.call_args.kwargs['write_timeout'],.5)
            finally:link.close()
    def test_stale_telemetry_stops_and_keepalive_does_not_need_params(self):
        s=Serial()
        with tempfile.TemporaryDirectory() as d,patch.object(C.serial,'Serial',return_value=s):
            link=C.Link('fake',logdir=d,verbose=False)
            try:
                until(lambda:b'ping\n' in s.commands)
                self.assertNotIn('host_timeout_ms',link.params)
                ready(s);until(lambda:link.rx_count==3)
                stop_count=s.commands.count(b'stop\n')
                link.last_telemetry_at=time.monotonic()-2
                until(lambda:s.commands.count(b'stop\n')>stop_count)
                self.assertFalse(link.send('auto'))
                # Fresh telemetry alone must not clear a missing STOP ack.
                for i in range(3):s.lines.put(frame(f'T {300+i*40} 0 0 0 0 0 0 -1 0 0 90 500'))
                until(lambda:link.rx_count==6)
                self.assertFalse(link.send('auto'))
                s.lines.put(frame('# STOP'));until(lambda:not link._motion_block_reason())
                self.assertNotIn(b'auto\n',s.commands)
            finally:link.close()
    def test_dropped_digit_or_minus_sign_cannot_refresh_data(self):
        s=Serial()
        with tempfile.TemporaryDirectory() as d,patch.object(C.serial,'Serial',return_value=s):
            link=C.Link('fake',logdir=d,verbose=False)
            try:
                good=frame('T 18021 0 -3.0879 0 0 0 0 -1 0 0 106 527')
                s.lines.put(good.replace(b'18021',b'1821'))
                s.lines.put(frame('= pc1 -0.80000').replace(b'-0.8',b'0.8'))
                s.lines.put(frame('E 174964 3416 1403 72 103 0 1 0').replace(b'1403',b'403'))
                s.lines.put(b'T 100 0 0 0 0 0 0 -1 0 0 90 500\n')
                until(lambda:link.bad_frames==4)
                self.assertEqual(link.rx_count,0);self.assertEqual(link.encoder_sequence,0)
                self.assertNotIn('pc1',link.params);self.assertIsNone(link.last_telemetry_at)
                self.assertFalse(link.send('auto'))
            finally:link.close()
    def test_lost_stop_ack_retries_and_block_reason_is_logged(self):
        s=Serial()
        with tempfile.TemporaryDirectory() as d,patch.object(C.serial,'Serial',return_value=s):
            link=C.Link('fake',logdir=d,verbose=False)
            try:
                stop_count=s.commands.count(b'stop\n')
                link._link_retry_at=time.monotonic()-2
                until(lambda:s.commands.count(b'stop\n')>stop_count)
                self.assertFalse(link.send('manual'))
                events=[json.loads(l) for l in Path(link.eventpath).read_text().splitlines()]
                self.assertTrue(any(e['direction']=='motion_blocked' and 'STOP acknowledgment' in e['text'] for e in events))
                ready(s);until(lambda:not link._motion_block_reason())
                self.assertIn('READY',link.link_status())
            finally:link.close()
if __name__=='__main__':unittest.main()
