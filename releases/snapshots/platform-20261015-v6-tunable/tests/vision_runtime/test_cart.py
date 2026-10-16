import unittest
import cv2
import numpy as np
from cartpole_vision.cart import CartTemplate

class CartTests(unittest.TestCase):
    def setUp(self):
        self.patch=np.random.default_rng(12).integers(40,230,(35,60,3),dtype=np.uint8)
    def image(self,x=200,y=150,duplicate=False):
        f=np.full((400,640,3),30,np.uint8);f[y:y+35,x:x+60]=self.patch
        if duplicate:f[y:y+35,450:510]=self.patch
        return f
    def test_translation_uses_fixed_anchor_without_arm(self):
        c=CartTemplate();c.select(self.image(),(200,150,60,35),(230,140))
        p,score,reason=c.detect(self.image(270,154))
        self.assertIsNotNone(p,reason)
        np.testing.assert_allclose(p,[300,144],atol=.2)
    def test_occlusion_and_ambiguity_are_not_measurements(self):
        c=CartTemplate();c.select(self.image(),(200,150,60,35),(230,140))
        self.assertIsNone(c.detect(np.zeros((400,640,3),np.uint8))[0])
        self.assertIsNone(c.detect(self.image(200,150,True))[0])
        self.assertIsNotNone(c.detect(self.image(280))[0])
    def test_low_texture_and_bad_rectangle_rejected(self):
        c=CartTemplate()
        with self.assertRaises(ValueError):c.select(self.image(),(0,0,40,40),(20,20))
        with self.assertRaises(ValueError):c.select(self.image(),(-1,150,60,35),(230,140))
if __name__=='__main__':unittest.main()
