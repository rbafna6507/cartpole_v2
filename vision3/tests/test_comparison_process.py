import json, socket, time, unittest
from pendulum_vision.comparison_process import ComparisonProcess
class ProcessTests(unittest.TestCase):
    def test_separate_process_tracks_without_camera_and_shuts_down(self):
        probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        c=ComparisonProcess(port=port)
        sender=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            for i in range(12):
                t=time.monotonic()
                p=dict(v=1,session='proc-test',seq=i+1,board_ms=i*10,host_t=t,theta=.2,theta_dot=0.,upright=3475,generation=0,valid=True,health={'status':'ok','age_s':0.})
                sender.sendto(json.dumps(p).encode(),('127.0.0.1',port))
                c.vision(dict(t=t,theta_rad=.2,angle_valid=True,confidence=.9))
                time.sleep(.01)
            deadline=time.monotonic()+2
            while True:
                data=c.snapshot()
                if data['status']['source']=='both' or time.monotonic()>deadline:break
                time.sleep(.01)
            self.assertEqual(data['status']['source'],'both')
            self.assertGreater(len(data['encoder']['samples']),5)
            self.assertAlmostEqual(data['status']['theta'],.2,delta=.01)
            old=data['epoch'];c.configure(-1,25);self.assertNotEqual(c.snapshot()['epoch'],old)
            self.assertEqual(c.encoder_sign,-1)
        finally:sender.close();c.close()
        self.assertFalse(c.process.is_alive())

    def test_failed_worker_does_not_break_vision_state(self):
        c=ComparisonProcess(port=0)
        try:
            c.process.terminate();c.process.join(timeout=2)
            start=time.monotonic()
            data=c.snapshot()
            self.assertLess(time.monotonic()-start,.5)
            self.assertEqual(data['status']['source'],'unavailable')
            self.assertIsNone(data['status']['theta'])
            self.assertIn('unavailable',data['status']['receiver_error'])
            self.assertEqual(data['encoder']['samples'],[])
            c.reset();c.configure(-1,25)
            self.assertEqual(c.snapshot()['status']['encoder_sign'],-1)
            self.assertFalse(c.vision(dict(t=time.monotonic(),theta_rad=.2,angle_valid=True)))
        finally:c.close()

    def test_late_queued_sample_from_old_calibration_is_discarded(self):
        c=ComparisonProcess(port=0)
        try:
            c.reset()
            now=time.monotonic()
            # A feeder can deliver an old sample after the reset RPC completed.
            c.queue.put_nowait((0,dict(t=now-.01,theta_rad=1.,angle_valid=True,confidence=.9)))
            c.vision(dict(t=now,theta_rad=.2,angle_valid=True,confidence=.9))
            deadline=time.monotonic()+1
            while True:
                data=c.snapshot()
                if data['fused']['samples'] or time.monotonic()>deadline:break
                time.sleep(.01)
            self.assertEqual(len(data['fused']['samples']),1)
            self.assertAlmostEqual(data['status']['theta'],.2,delta=.001)
        finally:c.close()
