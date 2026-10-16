"""Compare Python64 control to the actual archived native float32 tick.

Tolerances are absolute + relative, not bitwise claims. Wrapped angles compare
circular differences; +/-pi encoding is not a discrete controller mode waiver.
"""
import math
import random
import unittest
from dataclasses import asdict, replace
from cartpole_sdk.control import ReferenceController, load_tuned_parameters, gains
from cartpole_sdk.control.motion import State, advance, stopping_distance
from cartpole_sdk.control.reference import estimate, wrap
from oracle_support import NativeOracle

ERRORS = {}
PRIMITIVE_ERRORS = {}

def record_primitive(name, error):
    PRIMITIVE_ERRORS[name] = max(PRIMITIVE_ERRORS.get(name, 0), abs(error))
COVERED_MODES = set()

class ParityTests(unittest.TestCase):
    def setUp(self):
        self.p = load_tuned_parameters()
        self.native = NativeOracle(); self.native.__enter__()
        self.native.set_parameters(asdict(self.p))
        self.c = ReferenceController(self.p)
    def tearDown(self): self.native.__exit__(None,None,None)
    def reset(self,theta=0,now=0): self.native.reset(theta,now_us=now); self.c.reset(theta,now_us=now)
    def compare(self,theta,x,now,**kwargs):
        a=asdict(self.c.tick(theta,x,now_us=now,**kwargs)); b=self.native.tick(theta,x,now_us=now,**kwargs)
        for key in ('mode','brake_direction','enabled','upright_only'):
            self.assertEqual(a[key],b[key],(key,now,theta,x,a,b))
        COVERED_MODES.add(a['mode'])
        for key in ('theta','angle_hat','rate_hat','velocity','acceleration','demand','energy'):
            error=abs(wrap(a[key]-b[key])) if key in ('theta','angle_hat') else abs(a[key]-b[key])
            ERRORS[key]=max(ERRORS.get(key,0),error)
            tolerance=2e-4+2e-5*abs(b[key])
            self.assertLessEqual(error,tolerance,(key,now,a,b,error,tolerance))
        return a
    def test_primitive_gains_estimator_stopping_and_governor(self):
        k=self.native.probe('gains')
        for upright,prefix in ((False,''),(True,'bal_')):
            for field,value in asdict(gains(self.p,upright)).items():
                record_primitive('gains',value-k[prefix+field])
                self.assertAlmostEqual(value,k[prefix+field],places=5)
        rng=random.Random(1729)
        for _ in range(100):
            measured,angle,rate = rng.uniform(-math.pi,math.pi),rng.uniform(-math.pi,math.pi),rng.uniform(-100,100)
            py=estimate(measured,angle,rate,30)
            native=self.native.probe('estimate',measured,angle,rate,30,.001)
            record_primitive('estimator_angle',wrap(py[0]-native['angle_hat']))
            record_primitive('estimator_rate',py[1]-native['rate_hat'])
            self.assertLess(abs(wrap(py[0]-native['angle_hat'])),2e-6)
            self.assertLess(abs(py[1]-native['rate_hat']),3e-5)
            v,a=rng.uniform(-1.5,1.5),rng.uniform(-25,25)
            native=self.native.probe('stopping',v,a,25,150)
            record_primitive('stopping_distance',stopping_distance(v,a,25,150)-native['distance'])
            self.assertAlmostEqual(stopping_distance(v,a,25,150),native['distance'],places=6)
            x,request,brake=rng.uniform(-.249,.249),rng.uniform(-25,25),rng.choice((-1,0,1))
            py=advance(State(v,a,brake),x,request,1.5,25,25,150,.26,.001)
            native=self.native.probe('motion',v,a,brake,x,request,1.5,25,25,150,.26,.001)
            record_primitive('motion_velocity',py.velocity-native['velocity'])
            record_primitive('motion_acceleration',py.acceleration-native['acceleration'])
            self.assertEqual(py.brake_direction,native['brake_direction'])
            self.assertAlmostEqual(py.velocity,native['velocity'],places=6)
            self.assertAlmostEqual(py.acceleration,native['acceleration'],places=5)
    def test_hanging_startup_and_response_watch_fault(self):
        self.reset(math.pi)
        for i in range(2300): self.compare(math.pi,0,i*1000,command='auto' if i==0 else None)
        self.assertEqual(self.c.output.mode,4)
    def test_capture_balance_loss_and_wrapped_estimator(self):
        self.reset()
        for i in range(400):
            theta=0 if i<50 else .015*math.sin(i*.025) if i<200 else .95
            self.compare(theta,0,i*1000,command='auto' if i==0 else None)
        self.reset(math.pi-.001)
        for i in range(100): self.compare(-math.pi+.001 if i%2 else math.pi-.001,0,i*1000)
    def test_manual_deadline_both_rail_returns_and_hard_fault(self):
        for sign in (-1,1):
            self.reset(math.pi)
            for i in range(1100):
                x=sign*.246 if 400<=i<700 else sign*.23 if 700<=i<1000 else 0
                command='v' if i in (0,200,450) else None
                self.compare(math.pi,x,i*1000,command=command,command_value=sign*.1)
            self.compare(math.pi,sign*.251,1100000,command='manual')
            self.assertEqual(self.c.output.mode,4)
    def test_auto_rail_handoff_and_timeout(self):
        for sign in (-1,1):
            self.reset(math.pi)
            for i in range(600):
                x=sign*.246 if i<300 else sign*.23
                self.compare(math.pi,x,i*1000,command='auto' if i==0 else None)
        self.reset(math.pi)
        # Response watch disarms on measured motion so rail timeout owns fault.
        for i in range(8200): self.compare(math.pi-.1 if i else math.pi,.246,i*1000,command='auto' if i==0 else None)
        self.assertEqual(self.c.output.mode,4)
    def test_upright_reject_return_stop_and_timeout(self):
        self.reset(math.pi)
        self.assertEqual(self.compare(math.pi,0,0,command='bal')['mode'],0)
        self.reset(.05)
        for i in range(1500):
            theta=.05 if i<30 else 1
            x=.05 if 30<=i<300 else 0
            self.compare(theta,x,i*1000,command='bal' if i==0 else 'auto' if i==50 else None)
        self.assertEqual(self.c.output.mode,0)
        self.reset(); self.compare(0,0,0,command='bal')
        self.compare(1,.05,1000)
        self.compare(1,.05,10_001_000)
        self.compare(1,.05,10_002_000)
        self.assertEqual(self.c.output.mode,4)
    def test_spin_center_wait_release_and_timeout(self):
        # Deliberately low configurable spin thresholds exercise all phases
        # without constructing a fake private state or injected estimated rate.
        self.p=replace(self.p,spin_trip_rad_s=2,spin_resume_rad_s=.5)
        self.native.set_parameters(asdict(self.p)); self.c=ReferenceController(self.p)
        self.reset(math.pi)
        for i in range(600):
            theta=math.pi if i<5 else math.pi-.1
            x=.04 if 50<=i<200 else 0
            self.compare(theta,x,i*1000,command='auto' if i==0 else 'manual' if i==30 else None)
        self.reset(math.pi)
        self.compare(math.pi,0,0,command='auto')
        self.compare(math.pi-.1,.04,1000)
        self.compare(math.pi-.1,.04,10_001_000)
        self.compare(math.pi-.1,.04,10_002_000)
        self.assertEqual(self.c.output.mode,4)
    def test_exact_rail_and_upright_start_guards(self):
        for sign in (-1,1):
            for offset, expected in ((-1e-6,6),(0,4),(1e-6,4)):
                self.reset(math.pi)
                out=self.compare(math.pi,sign*(.25+offset),0,command='manual')
                self.assertEqual(out['mode'],expected)
            for offset, expected in ((-1e-6,3),(0,0),(1e-6,0)):
                theta=sign*(10*math.pi/180+offset)
                self.reset(theta)
                out=self.compare(theta,0,0,command='bal')
                self.assertEqual(out['mode'],expected)

    def test_manual_exact_deadline_and_encoder_bus_counter_reset(self):
        for start in (0,(2**32-100)*1000):
            self.reset(math.pi,start)
            self.compare(math.pi,0,start,command='v',command_value=.1)
            for i in range(1,250): self.compare(math.pi,0,start+i*1000)
            self.assertGreater(self.c.output.demand,0)
            out=self.compare(math.pi,0,start+250000)
            self.assertLess(out['demand'],0)
        self.reset(math.pi)
        for i in range(50):
            self.compare(math.pi,0,i*1000,encoder_ok=False,command='manual' if i==49 else None)
        # Original encUpdate rebuilds its bus at failure50, resetting the
        # consecutive counter; this probe preserves that archived behavior.
        self.assertEqual(self.c.output.mode,1)
        for i in range(50,55): self.compare(math.pi,0,i*1000,encoder_ok=False)
        self.assertEqual(self.c.output.mode,4)

    def test_encoder_hold_threshold_host_deadline_and_clock_rollover(self):
        self.reset(math.pi)
        for i in range(6): self.compare(math.pi if not i else 0,0,i*1000,encoder_ok=not i,command='auto' if i==0 else None)
        self.assertEqual(self.c.output.mode,4)
        for now in (0, (2**32-2)*1000, 2**32-2000):
            self.reset(math.pi,now)
            self.compare(math.pi,0,now,command='auto')
            self.compare(math.pi,0,now+1500000,host_fresh=False)
            self.assertEqual(self.c.output.mode,2)
            self.compare(math.pi,0,now+1501000,host_fresh=False)
            self.assertEqual(self.c.output.mode,4)

if __name__ == '__main__': unittest.main()
