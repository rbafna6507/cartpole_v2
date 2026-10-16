"""Optional camera-runtime tests; SDK core tests do not require camera packages."""
import importlib.util
import unittest

if any(importlib.util.find_spec(name) is None for name in ('cv2','flask','numpy')):
    raise unittest.SkipTest('Install the vision extra to run camera-runtime tests')
