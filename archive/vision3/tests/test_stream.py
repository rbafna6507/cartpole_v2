import importlib.util
import io
import struct
import unittest

class StreamTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('pendulum_vision.stream'),
                             'vision2 needs a bounded H.264 stream transport')
        from pendulum_vision import stream
        return stream

    def test_packet_parser_handles_partial_reads_and_preserves_frame_time(self):
        m=self.module()
        class Partial(io.BytesIO):
            def read(self,n=-1):return super().read(min(n,3))
        wire=struct.pack('!IQB',5,123456,1)+b'frame'
        self.assertEqual(m.read_packet(Partial(wire)),(123456,True,b'frame'))
        self.assertIsNone(m.read_packet(io.BytesIO(b'')))
        with self.assertRaises(EOFError):m.read_packet(io.BytesIO(wire[:-1]))

    def test_oversized_frame_is_rejected_before_allocating(self):
        m=self.module()
        with self.assertRaises(ValueError):
            m.read_packet(io.BytesIO(struct.pack('!IQB',100_000_000,0,1)))

    def test_new_viewer_waits_for_keyframe_and_slow_viewer_is_disconnected(self):
        m=self.module();hub=m.Broadcast(capacity=2)
        viewer=hub.subscribe()
        hub.publish(10,False,b'delta')
        self.assertTrue(viewer.empty())
        hub.publish(20,True,b'key');hub.publish(30,False,b'delta')
        self.assertEqual(m.read_packet(io.BytesIO(viewer.get_nowait())),(20,True,b'key'))
        hub.publish(40,False,b'next');hub.publish(50,False,b'overflow')
        self.assertIsNone(viewer.get_nowait())
        self.assertEqual(hub.clients,0)

    def test_closed_broadcast_wakes_viewer(self):
        m=self.module();hub=m.Broadcast();viewer=hub.subscribe();hub.close()
        self.assertIsNone(viewer.get_nowait())

    def test_video_frame_selection_never_reuses_pose_on_a_new_camera_frame(self):
        m=self.module()
        from pendulum_vision.app import Engine
        from test_detector import scene
        from types import SimpleNamespace
        import numpy as np
        engine=Engine();tracked=scene();engine.process(tracked,1.0,1)
        raw=np.zeros_like(tracked)
        camera=SimpleNamespace(get=lambda:(2,1.0125,raw))
        seq,t,frame=m.select_frame(camera,engine,'camera')
        self.assertEqual(seq,2);self.assertIs(frame,raw)
        seq,t,frame=m.select_frame(camera,engine,'tracked')
        self.assertEqual((seq,t),(1,1.0));self.assertFalse(np.array_equal(frame,tracked))
        self.assertTrue(np.array_equal(engine.frame,tracked))

    def test_mask_matches_encoder_dimensions_and_duplicate_work_is_skipped(self):
        m=self.module()
        from pendulum_vision.app import Engine
        from test_detector import scene
        from types import SimpleNamespace
        engine=Engine();frame=scene();engine.process(frame,1,1)
        camera=SimpleNamespace(get=lambda:(1,1,frame))
        self.assertEqual(m.select_frame(camera,engine,'mask')[2].shape,frame.shape)
        self.assertIsNone(m.select_frame(camera,engine,'tracked',after_seq=1))

    def test_video_rate_limit_tolerates_camera_jitter(self):
        m=self.module();self.assertTrue(hasattr(m,'RateGate'))
        gate=m.RateGate(80)
        self.assertEqual(sum(gate.accept(i/80+(.001 if i%2 else 0)) for i in range(160)),160)
        gate=m.RateGate(40)
        self.assertEqual(sum(gate.accept(i/80) for i in range(160)),80)

if __name__=='__main__':unittest.main()

class StreamApiTests(unittest.TestCase):
    def test_missing_encoder_returns_service_unavailable(self):
        from pendulum_vision.app import Engine,create_app
        client=create_app(Engine()).test_client()
        self.assertEqual(client.get('/video.h264').status_code,503)
        self.assertEqual(client.post('/api/video-mode',json={'mode':'camera'}).status_code,503)

    def test_route_sends_binary_frames_and_rejects_invalid_mode(self):
        from pendulum_vision.app import Engine,create_app
        from pendulum_vision.stream import Broadcast,VideoStream,read_packet
        from types import SimpleNamespace
        hub=Broadcast();video=SimpleNamespace(hub=hub,mode='camera')
        video.set_mode=lambda mode:VideoStream.set_mode(video,mode)
        engine=Engine();engine.video=video;client=create_app(engine).test_client()
        self.assertEqual(client.post('/api/video-mode',json={'mode':'unknown'}).status_code,400)
        self.assertEqual(client.post('/api/video-mode',json=[]).status_code,400)
        self.assertEqual(client.post('/api/video-mode',json={'mode':'tracked'}).status_code,200)
        self.assertEqual(video.mode,'tracked')
        import threading,time
        def publish():
            deadline=time.monotonic()+1
            while not hub.clients and time.monotonic()<deadline:time.sleep(.001)
            hub.publish(123,True,b'keyframe')
        worker=threading.Thread(target=publish);worker.start()
        response=client.get('/video.h264',buffered=False)
        self.assertEqual(response.status_code,200)
        self.assertEqual(read_packet(io.BytesIO(next(iter(response.response)))),(123,True,b'keyframe'))
        response.close();worker.join();self.assertEqual(hub.clients,0)
