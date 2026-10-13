import math
import unittest
from pendulum_vision import evaluate


class EvaluationTests(unittest.TestCase):
    def test_saved_camera_sequence_gaps_survive_benchmark(self):
        import tempfile,json,cv2
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'motion.avi';sidecar=root/'times.jsonl'
            writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),80,(960,600))
            self.assertTrue(writer.isOpened())
            for i in range(4):writer.write(evaluate.render_arm(i*.01))
            writer.release()
            sidecar.write_text(''.join(json.dumps(dict(t=i/80,seq=seq))+'\n' for i,seq in enumerate([20,21,24,25])))
            result=evaluate.benchmark(root/'result',frames=4,source=source,timestamps=sidecar)
            self.assertEqual(result['results']['vision3']['skipped_camera_frames'],2)

    def test_baseline_package_loads_independently(self):
        from pathlib import Path
        detector,estimator=evaluate.load_package(Path(__file__).parents[1],'comparison_vision')
        self.assertEqual(detector().__class__.__name__,'ArmDetector')
        self.assertEqual(estimator().__class__.__name__,'StateEstimator')
    def test_reference_angle_wrap_and_velocity_use_effective_time(self):
        self.assertTrue(hasattr(evaluate,'accuracy'))
        reference=[dict(t=i*.01,image_angle_rad=3.1+(i*.01)**2,
                        image_omega_rad_s=2*i*.01) for i in range(21)]
        rows=[dict(t=.1,image_angle_rad=3.11+2*math.pi,omega_rad_s=-.15,omega_effective_t=.075),
              dict(t=.15,image_angle_rad=3.1225,omega_rad_s=None,omega_effective_t=None)]
        result=evaluate.accuracy(rows,reference)
        self.assertLess(result['angle_error_deg']['rmse'],1e-9)
        self.assertLess(result['omega_effective_error_rad_s']['rmse'],1e-9)
        self.assertEqual(result['omega_effective_error_rad_s']['samples'],1)

    def test_reference_does_not_extrapolate_across_missing_truth(self):
        self.assertTrue(hasattr(evaluate,'accuracy'))
        reference=[dict(t=0,image_angle_rad=0),dict(t=1,image_angle_rad=1)]
        rows=[dict(t=.5,image_angle_rad=.5),dict(t=2,image_angle_rad=2)]
        result=evaluate.accuracy(rows,reference)
        self.assertEqual(result['angle_error_deg']['samples'],0)

    def test_synthetic_known_motion_detects_across_rotation(self):
        self.assertTrue(hasattr(evaluate,'render_arm'))
        from pendulum_vision.detector import ArmDetector
        d=ArmDetector(processing_width=640)
        for angle in (-2.5,-1.5,-.5,.5,1.5,2.5):
            r=d.detect(evaluate.render_arm(angle))
            self.assertIsNotNone(r.pose)
            self.assertLess(abs(math.atan2(math.sin(r.pose.angle-angle),math.cos(r.pose.angle-angle))),math.radians(1))


if __name__ == '__main__':unittest.main()
