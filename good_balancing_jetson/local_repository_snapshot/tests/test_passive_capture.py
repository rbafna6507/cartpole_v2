import math
import tempfile
import unittest
from pathlib import Path
from passive_capture import circular_summary, calibration_summary, validate_sample, PassiveSession

class PassiveCaptureTest(unittest.TestCase):
    def test_circular_mean_across_sensor_wrap(self):
        s=circular_summary([4095,0,1])
        self.assertLess(min(s['raw_mean'],4096-s['raw_mean']),1e-8)
        self.assertAlmostEqual(s['span_counts'],2)

    def test_eight_positions_and_closure_report_both_directions(self):
        for sign in [-1,1]:
            poses=[{'reference_deg':a,'summary':circular_summary([(137+sign*a/360*4096)%4096])} for a in range(0,361,45)]
            r=calibration_summary(poses)
            self.assertEqual(r['direction'],sign)
            self.assertAlmostEqual(r['closure_error_deg'],0)
            self.assertLess(max(abs(x) for x in r['offset_only_residual_deg']),1e-8)
        poses[-1]['summary']=circular_summary([300])
        self.assertGreater(abs(calibration_summary(poses)['closure_error_deg']),10)

    def test_invalid_or_enabled_samples_cannot_silently_qualify(self):
        s={'raw':0,'valid':1,'enabled':0,'status':32}
        validate_sample(s)
        for key,value in [('raw',4096),('valid',0),('enabled',1),('status',0)]:
            with self.assertRaises(RuntimeError):validate_sample(dict(s,**{key:value}))

    def test_commands_are_restricted_to_passive_acquisition(self):
        obj=PassiveSession.__new__(PassiveSession)
        class Link:
            def send(self,c):return True
        obj.link=Link()
        for cmd in ['stop','ping','enc','params','rate 25','rate 100']:obj.send(cmd)
        for cmd in ['auto','bal','home','upright 1802','zero','on','v 0.1','stop\nauto']:
            with self.assertRaises(ValueError):obj.send(cmd)


class GuidedWorkflowTest(unittest.TestCase):
    def test_eight_unique_poses_plus_closure_and_no_automatic_apply(self):
        from unittest.mock import patch
        from calibrate_encoder_8pos import collect
        class Session:
            report={}
            def save(self):pass
            def capture(self,label,seconds,**metadata):
                return dict(metadata,summary=circular_summary([(500-metadata['reference_deg']/360*4096)%4096]*20))
        s=Session()
        with patch('builtins.input',return_value='sensor side'),patch('calibrate_encoder_8pos.prompt') as prompts:
            collect(s,2)
        self.assertEqual(prompts.call_count,9)
        self.assertFalse(s.report['calibration_summary']['applied_to_firmware'])

    def test_fresh_snapshot_stop_handshake_and_incremental_files(self):
        import threading,time,json
        from unittest.mock import patch
        from collections import deque
        class FakeLink:
            def __init__(self,*args,**kwargs):
                self.lock=threading.Lock();self.encoder_sequence=0;self.encoder_samples=deque()
                self.rx_error=None;self.last_stop_ack_at=None;self.bad_frames=0;self.commands=[]
                self.params={};self.thread=type('Thread',(),{'is_alive':lambda _:True})()
            def send(self,c):
                self.commands.append(c)
                if c=='stop':self.last_stop_ack_at=time.monotonic()
                if c=='params':self.params=dict(serial_crc16=1,encoder_snapshot=1,encoder_upright_raw=1802,encoder_reference_saved=1,cart_steps_per_m=26666.67)
                if c=='enc':
                    self.encoder_sequence+=1
                    self.encoder_samples.append(dict(sequence=self.encoder_sequence,raw=45,board_ms=50*self.encoder_sequence,valid=1,enabled=0,status=32,i2c_errors=0))
                return True
            def close(self):self.commands.append('stop')
        with tempfile.TemporaryDirectory() as d,patch('passive_capture.Link',FakeLink):
            s=PassiveSession('test','fake',Path(d)/'result')
            link=s.link
            phase=s.capture('down',.12)
            self.assertGreaterEqual(phase['summary']['sample_count'],2)
            self.assertTrue((s.output/'down.jsonl').exists())
            s.close()
            report=json.loads((s.output/'report.json').read_text())
            self.assertFalse(report['complete'])
            self.assertEqual(report['parameters']['encoder_upright_raw'],1802)
            self.assertEqual(link.commands[-1],'stop')
            self.assertTrue(set(link.commands)<={'stop','params','enc','rate 100','rate 25'})

class CaptureFailureTest(unittest.TestCase):
    def test_incomplete_phase_on_missing_samples_and_interrupt(self):
        import json
        from unittest.mock import patch
        for failure in [RuntimeError('missing reply'),KeyboardInterrupt()]:
            with tempfile.TemporaryDirectory() as d:
                s=PassiveSession.__new__(PassiveSession);s.output=Path(d);s.report={'phases':[]}
                with patch.object(s,'sample',side_effect=failure):
                    with self.assertRaises(type(failure)):s.capture('broken',1)
                saved=json.loads((Path(d)/'report.json').read_text())
                self.assertFalse(saved['phases'][0]['complete'])
                self.assertIn('error',saved['phases'][0])

    def test_repeated_backward_and_wrapped_board_time(self):
        import threading
        from unittest.mock import patch
        class Link:
            lock=threading.Lock();encoder_sequence=0;encoder_samples=[]
        s=PassiveSession.__new__(PassiveSession);s.link=Link()
        def deliver(cmd):
            s.link.encoder_sequence+=1
            s.link.encoder_samples=[dict(raw=42,valid=1,enabled=0,status=32,board_ms=stamp)]
        with patch.object(s,'check'),patch.object(s,'send',side_effect=deliver):
            s.last_board_ms=1000
            for stamp in [1000,900]:
                with self.assertRaisesRegex(RuntimeError,'timestamp'):s.sample()
            s.last_board_ms=2**32-10;stamp=20
            self.assertEqual(s.sample()['board_ms'],20)

    def test_period_workflow_has_release_markers_and_both_baselines(self):
        from unittest.mock import patch
        from characterize_period import collect
        class Session:
            report={}
            phases=[]
            def save(self):pass
            def capture(self,label,seconds,**metadata):
                p=dict(label=label,**metadata,summary={'sample_count':600});self.phases.append(p);return p
        s=Session()
        with patch('characterize_period.prompt'),patch('characterize_period.time.sleep'),patch('builtins.input',return_value=''):
            collect(s,30,3,20)
        self.assertEqual(len(s.phases),9)
        decays=[p for p in s.phases if p['label'].endswith('decay')]
        self.assertEqual([p['release_side'] for p in decays],['left','right','left'])
        self.assertTrue(all('release_host_time_s' in p for p in decays))

if __name__=='__main__':unittest.main()
