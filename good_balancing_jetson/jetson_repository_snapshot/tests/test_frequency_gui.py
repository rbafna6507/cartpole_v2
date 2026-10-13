import importlib.util
import math
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bench',ROOT/'frequency_test_gui.py')
gui=importlib.util.module_from_spec(spec);spec.loader.exec_module(gui)

class FakeSerial:
    def __init__(self,*args,**kwargs):
        self.messages=queue.Queue();self.sent=[];self.closed=False
        self.position=0;self.state='IDLE';self.centered=0
    def write(self,data):
        cmd=data.decode().strip();self.sent.append(cmd)
        if cmd=='hello':self.messages.put('# FREQUENCY_TEST_V2 rail_mm=300 margin_mm=15 max_travel_mm=270 max_speed=2.34375000 steps_per_m=26666.66666667')
        elif cmd=='center':self.centered=1;self.messages.put('# CENTERED')
        elif cmd.startswith('run '):self.state='RUNNING';self.messages.put('# RUN 100 .25')
        elif cmd=='stop':self.state='IDLE';self.centered=0;self.messages.put('# STOP')
        elif cmd=='finish':self.state='IDLE';self.messages.put('# FINISH requested')
    def readline(self):
        try:return (self.messages.get_nowait()+'\n').encode()
        except queue.Empty:
            time.sleep(.01)
            return f'F 200 {self.state} 1 .01 .02 .03 .04 .01 .02 {self.centered}\n'.encode()
    def close(self):self.closed=True

class FrequencyTests(unittest.TestCase):
    def wait_for(self,predicate,timeout=1):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.01)
        self.fail('Timed out waiting for condition')
    def test_sine_units_limits_and_ramp(self):
        p=gui.describe(100,1)
        self.assertAlmostEqual(p['speed_peak'],.1*math.pi)
        self.assertAlmostEqual(p['acceleration_peak'],.2*math.pi**2)
        self.assertEqual(gui.waveform(100,1,0),[0]*4)
        self.assertTrue(gui.describe(300,.25)['errors'])
        self.assertTrue(gui.describe(270,5)['errors'])
        for value in [float('nan'),float('inf'),0,-1]:
            with self.assertRaises(ValueError):gui.describe(100,value)
        self.assertEqual(gui.waveform(100,1,10,3),[0]*4)
        self.assertEqual(gui.describe(100,.05)['ramp_s'],2.0)
        self.assertEqual(gui.describe(100,.25,3)['ramp_s'],3.0)
        self.assertAlmostEqual(gui.waveform(100,.05,2)[0],.05*math.sin(2*math.pi*.05*2))
        with self.assertRaises(ValueError):gui.describe(100,.25,float('nan'))
    def test_serial_handshake_center_run_and_lease_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=FakeSerial();b=gui.Bench(logdir=folder,serial_factory=lambda *a,**k:fake)
            self.addCleanup(b.close);b.connect('FAKE')
            self.wait_for(lambda:b.ready and b.last_rx)
            self.assertFalse(any(s.startswith('run') for s in fake.sent))
            with self.assertRaises(ValueError):b.command('run',100,.25)
            b.heartbeat();b.command('center');self.wait_for(lambda:b.centered)
            with self.assertRaises(ValueError):b.command('run',300,.25)
            b.command('run',100,.25);self.wait_for(lambda:b.state=='RUNNING')
            self.assertIn('run 100.000000 0.250000 2.000000',fake.sent)
            self.assertEqual(len(b.snapshot()['points'][-1]),7)
            b.browser_seen=time.monotonic()-1
            self.wait_for(lambda:'stop' in fake.sent)
            self.assertFalse(b.centered)
            b.close();self.assertTrue(fake.closed)
            self.assertIn('pulse_inferred_x_m',Path(b.logpath).read_text())
    def test_demo_never_opens_serial_and_closes_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            def forbidden(*a,**kw):self.fail('Demo opened a serial port')
            b=gui.Bench(demo=True,logdir=folder,serial_factory=forbidden)
            self.addCleanup(b.close);b.connect(None)
            self.wait_for(lambda:b.ready)
            b.command('center');b.command('run',100,.25)
            self.wait_for(lambda:len(b.points)>2)
            b.command('stop');self.assertFalse(b.centered)
            b.close();self.assertFalse(b.thread.is_alive())
    def test_stale_data_prevents_start(self):
        b=gui.Bench();b.ready=True;b.connected=True;b.centered=True;b.state='IDLE'
        with self.assertRaises(ValueError):b.command('run',100,.25)

    def test_stop_preempts_unacknowledged_run(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=FakeSerial()
            original=fake.write
            def write(data):
                if data.startswith(b'run '):
                    fake.sent.append(data.decode().strip())
                    fake.state='RUNNING'  # emulate missing acknowledgement
                else: original(data)
            fake.write=write
            b=gui.Bench(logdir=folder,serial_factory=lambda *a,**k:fake)
            self.addCleanup(b.close);b.connect('FAKE')
            self.wait_for(lambda:b.ready and b.last_rx)
            b.command('center');self.wait_for(lambda:b.centered)
            errors=[]
            def run():
                try:b.command('run',100,.25)
                except ValueError as exc:errors.append(str(exc))
            runner=threading.Thread(target=run);runner.start()
            self.wait_for(lambda:any(s.startswith('run ') for s in fake.sent))
            b.command('stop');runner.join(timeout=1)
            self.assertEqual(errors,['Cancelled by Stop.'])
            self.assertIn('stop',fake.sent)
            b.close()

if __name__=='__main__':unittest.main()
