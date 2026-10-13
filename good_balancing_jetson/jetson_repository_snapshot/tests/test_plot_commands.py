"""No serial hardware: plot command parsing, pasted input, and stop UI wiring."""
import importlib.util
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cartpole',ROOT/'cartpole.py')
console=importlib.util.module_from_spec(spec);spec.loader.exec_module(console)
class Link:
    params={}
    def __init__(self):self.commands=[]
    def send(self,command):self.commands.append(command)
    def recent(self):return [],{}
    def telemetry_warning(self):return "Waiting for telemetry"
class CommandsTest(unittest.TestCase):
    def setUp(self):
        self.link=Link();self.quit=False
        def quit_plot():self.link.send('stop');self.quit=True
        self.parser=console.PlotCommandInput(self.link,lambda:self.link.send('stop'),quit_plot,echo=lambda _:None)
    def feed(self,text):
        for key in text:self.parser.feed(key)
    def test_typed_stop_is_one_command_not_jog(self):
        self.feed('stop\n');self.assertEqual(self.link.commands,['stop'])
    def test_parameters_spaces_editing_and_auto_command(self):
        self.feed('set vmax 0.76\x7f5\n');self.feed('auto\n')
        self.assertEqual(self.link.commands,['set vmax 0.75','auto'])
    def test_link_command_is_local_while_plotting(self):
        self.link.link_status=lambda:'READY test status'
        output=[];self.parser.echo=output.append
        self.feed('link\n')
        self.assertEqual(self.link.commands,[])
        self.assertIn('READY test status\n',output)
    def test_blocked_auto_does_not_open_plot(self):
        class Blocked:
            port_name='fake';logpath='fake.csv';eventpath='fake.jsonl'
            def send(self,command):return False
        with patch('builtins.input',side_effect=['auto','bal','control','quit']),patch.object(console,'dashboard') as plot,patch.object(console.time,'sleep'):
            console.repl(Blocked())
        plot.assert_not_called()
    def test_immediate_stop_cancels_partial_line_and_quit_stops(self):
        self.feed('set jmax 1\x1b \nq\n')
        self.assertEqual(self.link.commands,['stop','stop','stop']);self.assertTrue(self.quit)
    def test_raw_reader_drains_pasted_line_and_eof(self):
        read,write=os.pipe()
        with os.fdopen(read) as stream,patch.object(sys,'stdin',stream):
            os.write(write,b'stop\n');os.close(write)
            with console.RawKeys() as keys:
                self.assertEqual(''.join(keys.poll()),'stop\n');self.assertTrue(keys.eof)
    def test_readonly_plot_stop_keys_button_and_terminal(self):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.backend_bases import KeyEvent,MouseEvent
        class Keys:
            eof=False
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def poll(self):
                if not getattr(self,'sent',False):self.sent=True;return list('stop\n')
                return []
        def show():
            limit=time.monotonic()+1
            while not self.link.commands and time.monotonic()<limit:time.sleep(.01)
            self.assertEqual(self.link.commands,['stop'])
            self.link.telemetry_warning=lambda: 'STALE TELEMETRY: motion state unknown'
            fig=plt.gcf();canvas=fig.canvas;canvas.draw()
            self.assertEqual(fig.texts[-1].get_text(),'STALE TELEMETRY: motion state unknown')
            self.assertEqual(fig.texts[-1].get_color(),'red')
            for key in [' ', 'escape']:
                canvas.callbacks.process('key_press_event',KeyEvent('key_press_event',canvas,key))
            self.assertEqual(self.link.commands,['stop']*3)
            # In automatic/data plots A/D/W/S must not issue jog commands.
            canvas.callbacks.process('key_press_event',KeyEvent('key_press_event',canvas,'s'))
            button=next(a for a in fig.axes if any(t.get_text()=='STOP / disable' for t in a.texts));x,y=button.transAxes.transform((.5,.5))
            for event in ['button_press_event','button_release_event']:
                canvas.callbacks.process(event,MouseEvent(event,canvas,x,y,button=1))
            self.assertEqual(self.link.commands,['stop']*4)
            button=next(a for a in fig.axes if any(t.get_text()=='START upright' for t in a.texts))
            x,y=button.transAxes.transform((.5,.5))
            for event in ['button_press_event','button_release_event']:
                canvas.callbacks.process(event,MouseEvent(event,canvas,x,y,button=1))
            self.assertEqual(self.link.commands,['stop']*4+['bal'])
        with patch.object(console,'RawKeys',Keys),patch.object(plt,'show',show):
            console.dashboard(self.link,interactive=False)
        self.assertEqual(self.link.commands,['stop']*4+['bal','stop'])
        plt.close('all')
if __name__=='__main__':unittest.main()
