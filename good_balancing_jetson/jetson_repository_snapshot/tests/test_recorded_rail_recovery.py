"""Replay sampled commanded braking states and their mirrors through real headers."""
from pathlib import Path
import json,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class RecordedRecoveryTest(unittest.TestCase):
    def test_controlled_release_rail_and_jerk_on_recorded_states(self):
        cases=json.loads((ROOT/'analysis/rail_recovery_v22_cases.json').read_text())['cases']
        lines=[]
        for c in cases:
            for sign in (1,-1):
                lines.append(' '.join(str(v) for v in [sign*c['x'],sign*c['v'],sign*c['a'],sign*c['side'],c['vmax'],c['amax'],c['jerk']]))
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'recovery'
            subprocess.run(['clang++','-std=c++11','-O2','-Wall','-Wextra','-Werror',str(ROOT/'tests/recorded_rail_recovery_test.cpp'),'-o',str(exe)],check=True)
            result=subprocess.run([str(exe)],input='\n'.join(lines)+'\n',text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            print(result.stdout.strip())
if __name__=='__main__':unittest.main()
