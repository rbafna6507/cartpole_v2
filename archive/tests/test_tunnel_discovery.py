"""Discovery tests keep SSH and TCP at their external boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vision_tunnel as tunnel

STABLE = '2601:408:c402:4f4d:7c33:6ac0:e348:c35'
TEMP = '2601:408:c402:4f4d:fd9f:2739:efc4:ecb3'

def address(ip, **kw):
    return dict(family='inet6', local=ip, scope='global', valid_life_time=100,
                preferred_life_time=50, **kw)

def payload(*rows):
    return json.dumps([dict(ifname='wlan0', flags=['UP'], addr_info=list(rows))])

class DiscoveryTests(unittest.TestCase):
    def test_stable_first_and_exclude_unusable_addresses(self):
        data = payload(address(TEMP, temporary=True), address(STABLE),
                       address('fd7a:115c:a1e0::1'), address('fe80::1'),
                       address('::1'), address('ff02::1'),
                       address('2606:4700::1111', deprecated=True))
        self.assertEqual(tunnel.candidates(data), [STABLE, TEMP])

    def test_expired_tentative_duplicate_and_down_interface(self):
        rows = [address(STABLE), address(STABLE), address(TEMP, tentative=True)]
        rows[0]['preferred_life_time'] = 0
        self.assertEqual(tunnel.candidates(payload(*rows)), [STABLE])
        self.assertEqual(tunnel.candidates(json.dumps([dict(flags=[], addr_info=rows)])), [])

    def test_malformed_or_non_address_input_rejected(self):
        for data in ('{}', '[1]', 'not json', payload(address('-oProxyCommand=bad'))):
            with self.subTest(data=data), self.assertRaises(ValueError):
                tunnel.candidates(data)

    def test_discovery_preserves_alias_identity_and_is_read_only(self):
        responses = [subprocess.CompletedProcess([], 0, 'hostname jetson\nport 22\nuser rbafna\n'),
                     subprocess.CompletedProcess([], 0, payload(address(STABLE)))]
        with patch.object(tunnel.subprocess, 'run', side_effect=responses) as run, \
             patch.object(tunnel.socket, 'create_connection', return_value=MagicMock()) as connect:
            cmd = tunnel.prepare(None, {})
        self.assertEqual(cmd[-1], 'jetson')
        self.assertIn('Hostname='+STABLE, cmd)
        self.assertIn('HostKeyAlias=jetson', cmd)
        self.assertIn('StrictHostKeyChecking=yes', cmd)
        self.assertIn('127.0.0.1:3095:127.0.0.1:3090', cmd)
        self.assertEqual(run.call_args_list[1].args[0][-7:],
                         ['ip', '-j', '-6', 'addr', 'show', 'scope', 'global'])
        connect.assert_called_once_with((STABLE, 22), timeout=2)

    def test_unreachable_stable_tries_temporary_without_changing_trust(self):
        responses = [subprocess.CompletedProcess([], 0, 'hostname peer\nport 2222\nhostkeyalias trusted-rig\n'),
                     subprocess.CompletedProcess([], 0, payload(address(STABLE), address(TEMP, temporary=True)))]
        with patch.object(tunnel.subprocess, 'run', side_effect=responses), \
             patch.object(tunnel.socket, 'create_connection', side_effect=[OSError('offline'), MagicMock()]):
            cmd = tunnel.prepare(None, {'JETSON_DISCOVERY_HOST':'rig'})
        self.assertIn('Hostname='+TEMP, cmd)
        self.assertIn('HostKeyAlias=trusted-rig', cmd)
        self.assertEqual(cmd[-1], 'rig')

    def test_no_reachable_candidate_does_not_silently_use_slow_route(self):
        responses = [subprocess.CompletedProcess([], 0, 'hostname jetson\nport 22\n'),
                     subprocess.CompletedProcess([], 0, payload(address(STABLE)))]
        with patch.object(tunnel.subprocess, 'run', side_effect=responses), \
             patch.object(tunnel.socket, 'create_connection', side_effect=OSError('offline')), \
             self.assertRaisesRegex(ValueError, 'explicit'):
            tunnel.prepare(None, {})

    def test_explicit_target_bypasses_discovery(self):
        with patch.object(tunnel.subprocess, 'run', side_effect=AssertionError('must not discover')):
            cmd = tunnel.prepare('jetson', {})
        self.assertEqual(cmd[-1], 'jetson')
        self.assertNotIn('HostKeyAlias=jetson', cmd)

    def test_failed_authenticated_discovery_propagates(self):
        with patch.object(tunnel.subprocess, 'run', side_effect=subprocess.CalledProcessError(255, 'ssh')), \
             self.assertRaisesRegex(ValueError, "bootstrap.*explicit"):

            tunnel.prepare(None, {})


class DiscoveryEdgeTests(unittest.TestCase):
    def responses(self, config='hostname bootstrap.example\nport 22\nuser fixture-user\n', data=None):
        return [subprocess.CompletedProcess([], 0, config),
                subprocess.CompletedProcess([], 0, data or payload(address(STABLE)))]

    def test_reject_failed_documentation_reserved_mapped_and_expired_addresses(self):
        rows = [address('2001:db8::1'), address('4000::1'), address('::ffff:8.8.8.8'),
                address(TEMP, dadfailed=True), address(STABLE)]
        rows[-1]['valid_life_time'] = 0
        self.assertEqual(tunnel.candidates(payload(*rows)), [])

    def test_flags_and_lifetimes_are_checked_and_forever_is_accepted(self):
        row = address(STABLE)
        row['valid_life_time'] = 'forever'
        row['preferred_life_time'] = 'forever'
        self.assertEqual(tunnel.candidates(payload(row)), [STABLE])
        for changes in ({'flags':['tentative']}, {'flags':['dadfailed']},
                        {'flags':['deprecated']}, {'preferred_life_time':0}):
            candidate = {**address(STABLE), **changes}
            self.assertEqual(tunnel.candidates(payload(candidate)), [])
        for bad in (True, -1, 'oops', 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tunnel.candidates(payload({**address(STABLE), 'valid_life_time':bad}))

    def test_reject_zone_id_duplicate_json_keys_and_malformed_shape(self):
        for bad in (payload(address(STABLE+'%wlan0')), '[{"flags":["UP"],"addr_info":{}}]',
                    '[{"flags":["UP"],"flags":[],"addr_info":[]}]'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tunnel.candidates(bad)

    def test_environment_target_also_bypasses_discovery(self):
        with patch.object(tunnel.subprocess, 'run', side_effect=AssertionError('must not discover')):
            cmd = tunnel.prepare(None, {'JETSON_SSH_TARGET':'operator@manual'})
        self.assertEqual(cmd[-1], 'operator@manual')

    def test_hostile_destinations_and_discovery_alias_fail_before_ssh(self):
        for target in ('-oProxyCommand=bad', 'user@host\n-oBad=yes', 'host;bad', '', 'user@host bad'):
            with self.subTest(target=target), patch.object(tunnel.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    tunnel.prepare(target, {})
                run.assert_not_called()
        with patch.object(tunnel.subprocess, 'run') as run, self.assertRaises(ValueError):
            tunnel.prepare(None, {'JETSON_DISCOVERY_HOST':'-Fbad'})
        run.assert_not_called()

    def test_discovery_timeouts_fail_with_explicit_fallback(self):
        for fail_at in (0, 1):
            responses = self.responses()
            responses[fail_at] = subprocess.TimeoutExpired('ssh', 15)
            with patch.object(tunnel.subprocess, 'run', side_effect=responses), self.assertRaisesRegex(ValueError, 'explicit'):
                tunnel.prepare(None, {})

    def test_bootstrap_is_strict_noninteractive_bounded_and_does_not_forward(self):
        with patch.object(tunnel.subprocess, 'run', side_effect=self.responses()) as run, \
             patch.object(tunnel.socket, 'create_connection', return_value=MagicMock()):
            cmd = tunnel.prepare(None, {})
        bootstrap = run.call_args_list[1]
        for option in ('BatchMode=yes', 'StrictHostKeyChecking=yes', 'ClearAllForwardings=yes', 'RemoteCommand=none'):
            self.assertIn(option, bootstrap.args[0])
        self.assertLessEqual(bootstrap.kwargs['timeout'], 20)
        self.assertIn('HostKeyAlias=bootstrap.example', cmd)
        self.assertIn('ProxyCommand=none', cmd)
        self.assertIn('ProxyJump=none', cmd)
        self.assertNotIn('BatchMode=yes', cmd)

    def test_probe_attempts_are_bounded_even_for_many_addresses(self):
        data = payload(*(address('2601:408::'+format(i, 'x')) for i in range(1, 101)))
        with patch.object(tunnel.subprocess, 'run', side_effect=self.responses(data=data)), \
             patch.object(tunnel.socket, 'create_connection', side_effect=OSError('offline')) as connect, \
             self.assertRaisesRegex(ValueError, 'explicit'):
            tunnel.prepare(None, {})
        self.assertLessEqual(connect.call_count, 8)

    def test_real_ssh_retains_config_user_keys_and_nonstandard_port_on_direct_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)/'config'
            config.write_text('Host jetson\n  HostName bootstrap.example\n  User fixture-user\n'
                              '  Port 2222\n  HostKeyAlias trusted-rig\n'
                              '  IdentityFile /tmp/fixture-private-key\n'
                              '  UserKnownHostsFile /tmp/fixture-trusted-keys\n'
                              '  ProxyJump jump.example\n  StrictHostKeyChecking no\n')
            parsed = subprocess.run([shutil.which('ssh'), '-G', '-F', str(config), 'jetson'],
                                    text=True, capture_output=True, check=True)
            with patch.object(tunnel.subprocess, 'run', side_effect=self.responses(config=parsed.stdout)), \
                 patch.object(tunnel.socket, 'create_connection', return_value=MagicMock()) as connect:
                cmd = tunnel.prepare(None, {})
            direct = subprocess.run([shutil.which('ssh'), '-G', '-F', str(config), *cmd[1:]],
                                    text=True, capture_output=True, check=True)
        self.assertIn('hostname '+STABLE+'\n', direct.stdout)
        self.assertIn('hostkeyalias trusted-rig\n', direct.stdout)
        self.assertIn('user fixture-user\n', direct.stdout)
        self.assertIn('port 2222\n', direct.stdout)
        self.assertIn('identityfile /tmp/fixture-private-key\n', direct.stdout)
        self.assertIn('userknownhostsfile /tmp/fixture-trusted-keys\n', direct.stdout)
        self.assertIn('stricthostkeychecking true\n', direct.stdout)
        self.assertNotIn('proxyjump jump.example\n', direct.stdout)
        connect.assert_called_once_with((STABLE, 2222), timeout=2)

    def test_nonstandard_port_without_hostkeyalias_keeps_bracketed_trust_identity(self):
        responses = self.responses(config='hostname bootstrap.example\nport 2222\nuser fixture-user\n')
        with patch.object(tunnel.subprocess, 'run', side_effect=responses), \
             patch.object(tunnel.socket, 'create_connection', return_value=MagicMock()):
            cmd = tunnel.prepare(None, {})
        self.assertIn('HostKeyAlias=[bootstrap.example]:2222', cmd)
        self.assertIn('CheckHostIP=no', cmd)
        self.assertIn('UpdateHostKeys=no', cmd)
        self.assertIn('User=fixture-user', cmd)
        self.assertIn('Port=2222', cmd)
