import unittest
import cv2
import numpy as np
from pendulum_vision.detector import ArmDetector


class SegmentationTests(unittest.TestCase):
    def test_full_resolution_geometry_preserves_saved_fixture_reference(self):
        from pathlib import Path
        image=cv2.imread(str(Path(__file__).parent/'fixtures'/'horizontal.png'))
        pose=ArmDetector(processing_width=960).detect(image).pose
        self.assertIsNotNone(pose)
        np.testing.assert_allclose(pose.pivot,[455.8747967479675,140.02845528455285],atol=1e-6)
        np.testing.assert_allclose(pose.bob,[660.0686487046889,186.24133099870437],atol=1e-6)

    def test_native_mask_is_exactly_equivalent_at_threshold_boundaries(self):
        rng = np.random.default_rng(124)
        frame = rng.integers(0, 256, (180, 240, 3), dtype=np.uint8)
        for chroma in (30, 0, -10):
            d = ArmDetector(chroma_min=chroma)
            self.assertTrue(hasattr(d, 'segment'))
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            b, g, r = [frame[:, :, i].astype(np.int16) for i in range(3)]
            expected = ((hsv[:, :, 0] >= 40) & (hsv[:, :, 0] <= 95)
                        & (hsv[:, :, 1] >= 110) & (g >= 60)
                        & (g-r >= chroma) & (g-b >= 8)).astype(np.uint8)*255
            expected = cv2.morphologyEx(expected, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
            actual, value = d.segment(frame)
            np.testing.assert_array_equal(actual, expected)
            np.testing.assert_array_equal(value, frame.max(axis=2))


if __name__ == '__main__': unittest.main()
