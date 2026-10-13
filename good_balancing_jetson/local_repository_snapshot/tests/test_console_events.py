import importlib.util
import json
import queue
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cartpole',ROOT/'cartpole.py')
console=importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)

class SerialStub:
    def __init__(self):
        self.lines=queue.Queue()
        self.commands=[]
        self.closed=False
    def write(self, data): self.commands.append(data)
    @property
    def in_waiting(self):return 1
    def read(self, size):
        try:
            value=self.lines.get(timeout=0.01)
            if isinstance(value,Exception):raise value
            return value
        except queue.Empty: return b''
    def close(self): self.closed=True

class ConsoleEventsTest(unittest.TestCase):
    def test_upright_requires_capability_and_snapshots_before_start(self):
        link=console.Link.__new__(console.Link)
        link._motion_block_reason=lambda: ""
        link._log_event=lambda *args: None
        link.params={};link.ser=SerialStub();link._send_lock=threading.Lock()
        self.assertFalse(link.send('bal'))
        self.assertEqual(link.ser.commands,[])
        link.params={'bal_fall_deg':50,'bal_start_deg':10}
        self.assertTrue(link.send('bal'))
        self.assertEqual(link.ser.commands,[b'params\n',b'bal\n'])

    def test_commands_parameters_faults_and_telemetry_survive_close(self):
        serial=SerialStub()
        with tempfile.TemporaryDirectory() as folder, patch.object(console.serial,'Serial',return_value=serial):
            link=console.Link('fake-port',logdir=folder,require_checksum=False)
            link.send('params')
            for line in [b'# firmware swingup-175mm-v3\n',b'= leff 0.16600\n',
                         b'! no pendulum response to cart command -> FAULT\n',
                         b'T 100 4 3.14 0 0.02 0 0 -1 0 0 90 500\n']:
                serial.lines.put(line)
            deadline=time.monotonic()+2
            while link.rx_count<1 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(link.rx_count,1)
            link.close()
            records=[json.loads(line) for line in Path(link.eventpath).read_text().splitlines()]
            text=[r['text'] for r in records]
            self.assertIn('params',text)
            self.assertIn('= leff 0.16600',text)
            self.assertIn('! no pendulum response to cart command -> FAULT',text)
            self.assertIn('stop',text)
            self.assertIn('100.0,4.0',Path(link.logpath).read_text())
            self.assertTrue(serial.closed)
            self.assertFalse(link.thread.is_alive())

    def test_corrupt_parameter_and_nonfinite_telemetry_do_not_kill_reader(self):
        serial=SerialStub()
        with tempfile.TemporaryDirectory() as folder, patch.object(console.serial,'Serial',return_value=serial):
            link=console.Link('fake-port',logdir=folder,require_checksum=False)
            for line in [b'= jmax broken\n',b'= amax_b nan\n',
                         b'T 100 nan 0 0 0 0 0 -1 0 0 90 500\n',
                         b'T 101 2 0 0 0 0 0 -1 0 0 90 500\n',b'T 102 2 0 0 0 0 0 -1 0 0 90 500\n',b'T 103 2 0 0 0 0 0 -1 0 0 90 500\n',b'# STOP\n',b'= jmax 70\n']:
                serial.lines.put(line)
            deadline=time.monotonic()+2
            while link.params.get('jmax')!=70 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(link.params['jmax'],70)
            self.assertEqual(link.rx_count,3);self.assertTrue(link.thread.is_alive())
            self.assertEqual(link.telemetry_warning(),'')
            link.last_telemetry_at=time.monotonic()-3
            self.assertIn('STALE TELEMETRY',link.telemetry_warning())
            link.close()
            records=[json.loads(line) for line in Path(link.eventpath).read_text().splitlines()]
            self.assertEqual(sum(r['direction']=='parse_error' for r in records),3)

    def test_serial_error_is_visible_and_recorded(self):
        serial=SerialStub()
        with tempfile.TemporaryDirectory() as folder, patch.object(console.serial,'Serial',return_value=serial):
            link=console.Link('fake-port',logdir=folder,reconnect=False,require_checksum=False)
            serial.lines.put(OSError('device disconnected'))
            link.thread.join(timeout=2)
            self.assertFalse(link.thread.is_alive())
            self.assertIn('device disconnected',link.telemetry_warning())
            self.assertEqual(link.rx_rate,0)
            link.close()
            records=[json.loads(line) for line in Path(link.eventpath).read_text().splitlines()]
            self.assertTrue(any(r['direction']=='reader_error' and 'device disconnected' in r['text'] for r in records))

if __name__=='__main__':unittest.main()
