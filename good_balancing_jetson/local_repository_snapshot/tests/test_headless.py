import os
import unittest
from unittest.mock import Mock, patch
import cartpole

class HeadlessTest(unittest.TestCase):
    def link(self):
        link=Mock();link.text_mode=False;link.params={}
        return link

    def test_explicit_text(self):
        link=self.link();link.text_mode=True
        with patch.object(cartpole,'text_dashboard') as text:
            cartpole.dashboard(link)
            text.assert_called_once_with(link,False)
        link.send.assert_not_called()

    def test_linux_without_display(self):
        link=self.link()
        with patch.dict(os.environ,{},clear=True),patch.object(cartpole.sys,'platform','linux'),patch.object(cartpole,'text_dashboard') as text:
            cartpole.dashboard(link)
            text.assert_called_once_with(link,False)
        link.send.assert_not_called()

    def test_agg_with_display_falls_back_without_stop(self):
        import matplotlib
        matplotlib.use('Agg',force=True)
        link=self.link()
        with patch.dict(os.environ,{'DISPLAY':':99'}),patch.object(cartpole,'text_dashboard') as text:
            cartpole.dashboard(link)
            text.assert_called_once_with(link,False)
        link.send.assert_not_called()

    def test_eof_still_stops(self):
        link=self.link()
        keys=Mock();keys.poll.return_value=[];keys.eof=True
        with patch.object(cartpole,'RawKeys') as raw:
            raw.return_value.__enter__.return_value=keys
            cartpole.text_dashboard(link)
        link.send.assert_called_with('stop')
