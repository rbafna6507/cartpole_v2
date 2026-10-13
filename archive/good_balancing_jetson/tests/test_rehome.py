"""Return-to-home guards: wrong direction, blind motion, resets, and runaway."""
import unittest
import threading
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
import cartpole

class RehomeTest(unittest.TestCase):
    def state(self, **changes):
        s=dict(t_ms=1000,mode=0,x=.1,v=0,theta=3.1,theta_dot=0)
        s.update(changes)
        return s

    def controller(self, **changes):
        self.assertTrue(hasattr(cartpole,'RehomeController'),'rehome controller missing')
        return cartpole.RehomeController(self.state(**changes),.26,0)

    def test_both_directions_converge_without_redefining_home(self):
        for x in [-.2,.2]:
            c=self.controller(x=x);s=self.state(x=x)
            for i in range(400):
                v=c.update(s,i*.05)
                if v is None:break
                self.assertLessEqual(abs(v),.04)
                self.assertLess(v*s['x'],0)
                s.update(x=s['x']+v*.05,v=v,mode=1,t_ms=1000+50*(i+1))
            self.assertLess(abs(s['x']),.001)
            self.assertLess(abs(s['v']),.005)

    def test_refuses_moving_upright_faulted_or_outside_rail_start(self):
        for changes in [dict(v=.1),dict(mode=3),dict(theta=0),dict(theta_dot=1),dict(x=.256),dict(x=float('nan'))]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.controller(**changes)

    def test_abort_on_reset_fault_speed_limit_and_timeout(self):
        for changes,now in [(dict(t_ms=999),.1),(dict(mode=4),.1),(dict(v=.07),.1),(dict(x=.256),.1),({},21)]:
            c=self.controller()
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):c.update(self.state(**changes),now)

    def test_missing_or_invalid_rail_is_rejected(self):
        for rail in [None,0,float('nan'),float('inf')]:
            self.assertTrue(hasattr(cartpole,'RehomeController'),'rehome controller missing')
            with self.assertRaises(ValueError):cartpole.RehomeController(self.state(),rail,0)

if __name__=='__main__':unittest.main()

class RehomeIntegrationTest(unittest.TestCase):
    def link(self):
        commands=[]
        s=dict(t_ms=1000,mode=0,x=.1,v=0,theta=3.1,theta_dot=0)
        return SimpleNamespace(params={'rail':.26},last_telemetry_at=10,
            telemetry_warning=lambda:'',lock=threading.Lock(),
            buf={k:[v] for k,v in s.items()},commands=commands,
            send=lambda command:commands.append(command) is None)

    def test_stale_mid_return_stops_without_home(self):
        link=self.link()
        keys=SimpleNamespace(poll=lambda:[],eof=False)
        with patch.object(cartpole,'RawKeys',return_value=nullcontext(keys)),patch.object(cartpole.time,'monotonic',return_value=10),patch.object(cartpole.time,'sleep',side_effect=lambda _:setattr(link,'last_telemetry_at',9)):
            self.assertFalse(cartpole.rehome(link))
        self.assertEqual(link.commands,['v -0.04000','stop'])

    def test_keyboard_cancel_sends_stop(self):
        link=self.link();keys=SimpleNamespace(poll=lambda:[' '],eof=False)
        with patch.object(cartpole,'RawKeys',return_value=nullcontext(keys)),patch.object(cartpole.time,'monotonic',return_value=10):
            self.assertFalse(cartpole.rehome(link))
        self.assertEqual(link.commands,['stop'])

    def test_already_centered_completes_with_stop_only(self):
        link=self.link();link.buf['x']=[0];keys=SimpleNamespace(poll=lambda:[],eof=False)
        with patch.object(cartpole,'RawKeys',return_value=nullcontext(keys)),patch.object(cartpole.time,'monotonic',return_value=10):
            self.assertTrue(cartpole.rehome(link))
        self.assertEqual(link.commands,['stop'])

    def test_plot_does_not_forward_unknown_firmware_rehome(self):
        link=self.link();output=[]
        parser=cartpole.PlotCommandInput(link,lambda:None,lambda:None,echo=output.append)
        for key in 'rehome\n':parser.feed(key)
        self.assertEqual(link.commands,[])
        self.assertIn('>>>',''.join(output))
