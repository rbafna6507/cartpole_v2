"""Check SSH invocation without contacting a host or opening a tunnel."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'vision-tunnel.sh'


class TunnelTests(unittest.TestCase):
    def run_script(self, *args, key_name="known hosts", **overrides):
        self.assertTrue(SCRIPT.is_file(), 'tunnel script is missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / 'ssh'
            fake.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                            'open(os.environ["SSH_CAPTURE"],"w").write(json.dumps(sys.argv[1:]))\n'
                            'sys.exit(int(os.environ.get("SSH_RESULT","0")))\n')
            fake.chmod(0o755)
            keyfile = root / key_name
            keyfile.write_text('test fixture\n')
            capture = root / 'arguments.json'
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'SSH_CAPTURE': str(capture), 'JETSON_KNOWN_HOSTS': str(keyfile),
                   'JETSON_SSH_TARGET': 'operator@test-device', **overrides}
            result = subprocess.run(['bash', str(SCRIPT), *args], cwd='/', env=env,
                                    text=True, capture_output=True, timeout=5)
            argv = json.loads(capture.read_text()) if capture.exists() else None
            return result, argv

    def test_local_only_forward_and_verified_host_without_remote_command(self):
        result, argv = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('-N', argv)
        self.assertIn('StrictHostKeyChecking=yes', argv)
        self.assertIn('ExitOnForwardFailure=yes', argv)
        self.assertIn('127.0.0.1:3095:127.0.0.1:3090', argv)
        self.assertEqual(argv[-1], 'operator@test-device')
        self.assertIn('http://127.0.0.1:3095/', result.stdout)

    def test_real_ssh_parser_accepts_one_known_hosts_path_with_spaces(self):
        ssh = shutil.which('ssh')
        self.assertIsNotNone(ssh, 'OpenSSH is required for the offline parser check')
        key_name = 'known ' * 32 + '"quoted" \\hosts'
        result, argv = self.run_script(key_name=key_name)
        self.assertEqual(result.returncode, 0, result.stderr)
        # -G resolves configuration only: it does not connect to the target.
        parsed = subprocess.run([ssh, '-G', '-F', '/dev/null', *argv],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        key_line = next(line for line in parsed.stdout.splitlines()
                        if line.startswith('userknownhostsfile '))
        self.assertTrue(key_line.endswith('/' + key_name), key_line)

    def test_override_ports_and_propagate_ssh_failure(self):
        result, argv = self.run_script('operator@other-device', LOCAL_PORT='4001',
                                       REMOTE_PORT='4002', SSH_RESULT='23')
        self.assertEqual(result.returncode, 23)
        self.assertIn('127.0.0.1:4001:127.0.0.1:4002', argv)
        self.assertEqual(argv[-1], 'operator@other-device')

    def test_reject_invalid_ports_and_option_like_destinations(self):
        for overrides in ({'LOCAL_PORT': '0'}, {'LOCAL_PORT': '65536'},
                          {'REMOTE_PORT': 'oops'}, {'JETSON_SSH_TARGET': '-oProxyCommand=bad'}):
            with self.subTest(overrides=overrides):
                result, argv = self.run_script(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(argv)


if __name__ == '__main__':
    unittest.main()
