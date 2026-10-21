import math
import unittest
import cv2
import numpy as np
from cartpole_vision.detector import ArmDetector


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

def partial_rim_scene(radius=16, length=60, shaft_width=4):
    """A narrow real contour whose fitted circle center falls outside its crop."""
    image = np.full((600,800,3), 35, np.uint8)
    rim = np.zeros(image.shape[:2], np.uint8)
    cv2.circle(rim, (400+radius, 200+length), radius, 255, -1)
    rim[:,409:] = 0
    image[rim > 0] = (90,200,10)
    cv2.line(image, (402,200), (402,200+length), (90,200,10), shaft_width)
    cv2.circle(image, (402,202), 2, (25,25,25), -1)
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
    def test_out_of_bounds_shaft_samples_reject_candidate_and_recover(self):
        # Real contour fitting produces high indices for the short partial rim
        # and negative indices for the mirrored longer rim. Rotate to exercise
        # both image axes; no fitted coordinates or confidence gates are mocked.
        for negative in (False, True):
            malformed = (cv2.flip(partial_rim_scene(36,160,3), 1) if negative
                         else partial_rim_scene())
            for rotate in (False, True):
                with self.subTest(negative=negative, rotate=rotate):
                    image = (cv2.rotate(malformed, cv2.ROTATE_90_CLOCKWISE)
                             if rotate else malformed)
                    detector = ArmDetector()
                    result = detector.detect(image)
                    self.assertIsNone(result.pose)
                    self.assertEqual(result.reason, 'no reliable arm geometry')
                    self.assertEqual(result.candidates, 0)
                    self.assertIsNotNone(detector.detect(scene(clutter=False)).pose)

    def test_zero_area_green_fragments_preserve_valid_geometry(self):
        clean = scene(clutter=False)
        noisy = clean.copy()
        # Isolated green pixels and single-pixel lines are zero-area polygons.
        # They must neither create false arms nor change the measured arm.
        for y in range(25, 175, 8):
            for x in range(25, 175, 8):
                noisy[y, x] = (90, 200, 10)
                noisy[y, x+3:x+5] = (90, 200, 10)
        expected = ArmDetector().detect(clean)
        result = ArmDetector().detect(noisy)
        self.assertIsNotNone(expected.pose)
        self.assertEqual(expected.pose, result.pose)
        self.assertEqual((expected.reason, expected.candidates),
                         (result.reason, result.candidates))
        fragments = np.full_like(clean, 35)
        fragments[:180, :180] = noisy[:180, :180]
        self.assertIsNone(ArmDetector().detect(fragments).pose)

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
