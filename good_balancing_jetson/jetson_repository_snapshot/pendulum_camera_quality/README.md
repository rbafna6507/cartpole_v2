# Multiple-candidate tracking fix

Stop the camera process. Replace ONLY green_arm.py beside the track_camera.py
you actually launch. Keep the latest vision.py/track_camera.py from the previous
tracking fix and your existing tracker.json. Restart with your usual command,
reload the browser, click the center of the pivot screw, then set hanging zero.

The previous implementation required exactly one nearby green contour and one
dark contour. Nearby green hardware and multiple dark spots caused rejection.
This version evaluates all candidate pairs, checks an elongated arm silhouette,
checks the pivot is near its end, and chooses the geometrically valid pivot
closest to the click/last detected pivot. Near ties remain invalid. It retains
the dark-screw color-tint fix and does not fabricate missing measurements.

Tested: synthetic one/two/three green regions; three dark screw candidates;
ambiguous near ties rejected; blank frame rejected; supplied snapshot at
960/1920/2048px widths. Live motion/occlusion remains to be verified.

To run the synthetic tests from this folder:
    python test_candidates.py /path/to/your/tracker.json
