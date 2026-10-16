"""Runs on Jetson with its existing system GStreamer Python runtime."""
import io
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import cv2
import numpy as np
from cartpole_vision.stream import read_packet

@unittest.skipUnless(os.environ.get('VISION2_GST_TESTS')=='1','Requires Jetson system GStreamer; set VISION2_GST_TESTS=1')
class EncoderTests(unittest.TestCase):
    def test_encode_preserves_frame_count_timing_and_decodes(self):
        source=bytearray();times=[]
        for i in range(50):
            frame=np.full((200,320,3),35,np.uint8)
            cv2.rectangle(frame,(10+i*2,40),(50+i*2,90),(0,220,20),-1)
            t=100+i*.0125+(0.025 if i>=25 else 0)
            times.append(t);raw=frame.tobytes();source.extend(struct.pack('!dI',t,len(raw))+raw)
        helper=Path(__file__).parents[1]/'cartpole_vision'/'gst_encoder.py'
        p=subprocess.run(['/usr/bin/python3',str(helper),'320','200','80','2000'],input=source,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr.decode())
        packets=[];data=io.BytesIO(p.stdout)
        while (packet:=read_packet(data)) is not None:packets.append(packet)
        self.assertEqual(len(packets),50,p.stderr.decode())
        self.assertTrue(packets[0][1]);self.assertTrue(packets[40][1])
        for packet,t in zip(packets,times):self.assertAlmostEqual(packet[0],round((t-100)*1e6),delta=2)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.h264';path.write_bytes(b''.join(p[2] for p in packets))
            cap=cv2.VideoCapture(str(path));count=0
            while True:
                ok,frame=cap.read()
                if not ok:break
                self.assertEqual(frame.shape,(200,320,3));count+=1
            cap.release();self.assertEqual(count,50)
