import math
import unittest
import cv2
import numpy as np
from pendulum_vision.detector import ArmDetector


def scene(angle=0, pivot=(320,240), clutter=True):
    image = np.full((600,800,3), 35, np.uint8)
    if clutter:
        cv2.rectangle(image,(30,30),(760,560),(35,55,35),-1) # old threshold joins this background
        cv2.rectangle(image,(40,50),(110,115),(80,190,0),-1)
    p=np.array(pivot,float)
    v=np.array([math.sin(angle),math.cos(angle)])
    bob=p+180*v
    cv2.line(image,tuple(p.astype(int)),tuple(bob.astype(int)),(90,200,10),22)
    cv2.circle(image,tuple(bob.astype(int)),29,(90,200,10),-1)
    cv2.circle(image,tuple(p.astype(int)),6,(25,25,25),-1)
    for a in np.arange(0,2*math.pi,math.pi/3):
        hole=bob+19*np.array([math.cos(a),math.sin(a)])
        cv2.circle(image,tuple(hole.astype(int)),3,(25,25,25),-1)
    return image

class DetectorTests(unittest.TestCase):
    def test_rotations_and_background(self):
        for deg in range(-180,180,30):
            with self.subTest(deg=deg):
                result=ArmDetector().detect(scene(math.radians(deg)))
                self.assertIsNotNone(result.pose,result.reason)
                self.assertLess(np.linalg.norm(np.array(result.pose.pivot)-[320,240]),3)
                error=math.atan2(math.sin(result.pose.angle-math.radians(deg)),math.cos(result.pose.angle-math.radians(deg)))
                self.assertLess(abs(math.degrees(error)),1.5)
    def test_blank_and_occlusion_recover_without_click(self):
        d=ArmDetector()
        self.assertIsNotNone(d.detect(scene()).pose)
        self.assertIsNone(d.detect(np.zeros((600,800,3),np.uint8)).pose)
        self.assertIsNotNone(d.detect(scene(.5)).pose)
    def test_two_plausible_arms_are_ambiguous(self):
        image=np.maximum(scene(0,(230,200),False),scene(0,(570,200),False))
        self.assertIsNone(ArmDetector().detect(image).pose)
    def test_selection_does_not_limit_cart_travel(self):
        d=ArmDetector();d.select(320,240)
        self.assertIsNotNone(d.detect(scene()).pose)
        self.assertIsNotNone(d.detect(scene(pivot=(460,240))).pose)

    def test_bright_rim_and_weight_holes_do_not_move_endpoints(self):
        from pathlib import Path
        for name,expected_bob in [("bright.png",[467,351]),("horizontal.png",[660,187])]:
            image=cv2.imread(str(Path(__file__).parent/"fixtures"/name))
            r=ArmDetector().detect(image)
            self.assertIsNotNone(r.pose,r.reason)
            self.assertLess(np.linalg.norm(np.array(r.pose.pivot)-[456,137]),4)
            self.assertLess(np.linalg.norm(np.array(r.pose.bob)-expected_bob),5)

    def test_known_live_still(self):
        from pathlib import Path
        p=Path(__file__).parent/'fixtures'/'live.png'
        image=cv2.imread(str(p))
        self.assertIsNotNone(image)
        result=ArmDetector().detect(image)
        self.assertIsNotNone(result.pose,result.reason)
        self.assertLess(np.linalg.norm(np.array(result.pose.pivot)-[488,137]),4)
        self.assertLess(abs(math.degrees(result.pose.angle)-2.0),2)

if __name__=='__main__':unittest.main()
