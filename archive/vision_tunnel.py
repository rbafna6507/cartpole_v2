"""Discover a direct IPv6 route using an already trusted SSH bootstrap alias.

Importing this module never connects. ``prepare`` performs read-only discovery
unless an explicit destination is supplied; ``main`` starts the local forward.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
from collections.abc import Mapping

_FALLBACK = 'Pass an explicit destination (for example: ./archive/vision-tunnel.sh jetson) or set JETSON_SSH_TARGET.'
_MAX_PROBES = 8


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate key in address JSON: ' + key)
        result[key] = value
    return result


def _lifetime(value):
    if value == 'forever':
        return True
    if type(value) is not int or value < 0:
        raise ValueError('Invalid IPv6 address lifetime.')
    return value > 0


def candidates(ip_json: str) -> list[str]:
    """Return usable public IPv6 addresses, stable before temporary addresses.

    Only active interfaces and preferred addresses are considered. Malformed
    address data fails closed; no value from discovery becomes a shell command.
    """
    try:
        interfaces = json.loads(ip_json, object_pairs_hook=_unique_object)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid address JSON from bootstrap host.') from exc
    if not isinstance(interfaces, list):
        raise ValueError('Address JSON must be a list of interfaces.')
    ranked = {}
    for interface in interfaces:
        if not isinstance(interface, dict):
            raise ValueError('Invalid interface in address JSON.')
        flags, rows = interface.get('flags'), interface.get('addr_info')
        if (not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags)
                or not isinstance(rows, list)):
            raise ValueError('Invalid interface flags or addresses.')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Invalid address record.')
            if row.get('family') != 'inet6' or row.get('scope') != 'global':
                continue
            local = row.get('local')
            if not isinstance(local, str) or '%' in local:
                raise ValueError('Invalid IPv6 address in discovery data.')
            try:
                ip = ipaddress.IPv6Address(local)
            except ipaddress.AddressValueError as exc:
                raise ValueError('Invalid IPv6 address in discovery data.') from exc
            address_flags = row.get('flags', [])
            if not isinstance(address_flags, list) or not all(isinstance(flag, str) for flag in address_flags):
                raise ValueError('Invalid IPv6 address flags.')
            for flag in ('deprecated', 'tentative', 'dadfailed', 'temporary', 'secondary'):
                if flag in row and type(row[flag]) is not bool:
                    raise ValueError('Invalid IPv6 status flag.')
            valid = _lifetime(row.get('valid_life_time'))
            preferred = _lifetime(row.get('preferred_life_time'))
            if ('UP' not in flags or not valid or not preferred or not ip.is_global
                    or ip.is_reserved or ip.is_multicast or ip.ipv4_mapped is not None
                    or any(row.get(flag, False) or flag in address_flags
                           for flag in ('deprecated', 'tentative', 'dadfailed'))):
                continue
            temporary = bool(row.get('temporary') or row.get('secondary')
                             or 'temporary' in address_flags or 'secondary' in address_flags)
            normalized = str(ip)
            ranked[normalized] = min(ranked.get(normalized, 1), int(temporary))
    return sorted(ranked, key=ranked.get)


def _destination(value: str) -> str:
    if (not isinstance(value, str) or not value or value.startswith('-')
            or re.fullmatch(r'[A-Za-z0-9_.:@%+\[\]-]+', value) is None):
        raise ValueError('Invalid SSH destination.')
    return value


def _port(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r'[0-9]{1,5}', value) is None or not 1 <= int(value) <= 65535:
        raise ValueError('Ports must be integers from 1 to 65535.')
    return str(int(value))


def _quoted(value: str) -> str:
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Invalid SSH configuration value.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def prepare(target: str | None, env: Mapping[str, str]) -> list[str]:
    """Build tunnel SSH argv, discovering through ``jetson`` when unspecified."""
    local_port = _port(env.get('LOCAL_PORT', '3095'))
    remote_port = _port(env.get('REMOTE_PORT', '3090'))
    common = ['-T', '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
              '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1',
              '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no']
    known_hosts = env.get('JETSON_KNOWN_HOSTS', '')
    if known_hosts:
        quoted = _quoted(known_hosts)
        if not Path(known_hosts).is_file() or not os.access(known_hosts, os.R_OK):
            raise ValueError('Verified host-key file is missing. Set JETSON_KNOWN_HOSTS to your verified known_hosts file.')
        common += ['-o', 'UserKnownHostsFile=' + quoted]
    explicit = target if target is not None else env.get('JETSON_SSH_TARGET') or None
    direct_options = []
    if explicit is not None:
        destination = _destination(explicit)
    else:
        destination = _destination(env.get('JETSON_DISCOVERY_HOST', 'jetson'))
        discovery_options = common + ['-o', 'BatchMode=yes', '-o', 'ClearAllForwardings=yes',
                                      '-o', 'RemoteCommand=none', '-o', 'SessionType=default']
        try:
            config = subprocess.run(['ssh', '-G', *discovery_options, destination],
                                    check=True, text=True, capture_output=True, timeout=5)
            settings = {}
            for line in config.stdout.splitlines():
                name, separator, value = line.partition(' ')
                if separator:
                    settings.setdefault(name.lower(), value.strip())
            hostname = settings.get('hostname')
            if not hostname:
                raise ValueError('SSH configuration has no effective hostname.')
            port = int(_port(settings.get('port', '22')))
            identity = settings.get('hostkeyalias')
            if not identity or identity == 'none':
                identity = hostname if port == 22 else f'[{hostname}]:{port}'
            # HostKeyAlias is a known-hosts lookup identity, never an arbitrary
            # discovered address. Keep it exactly as resolved for the bootstrap.
            _destination(identity)
            discovered = subprocess.run(
                ['ssh', *discovery_options, destination,
                 'ip', '-j', '-6', 'addr', 'show', 'scope', 'global'],
                check=True, text=True, capture_output=True, timeout=15)
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError('Authenticated bootstrap discovery is unavailable. '
                             f'Check that ssh {destination} works with a trusted key (load/unlock it if needed). '
                             + _FALLBACK) from exc
        addresses = candidates(discovered.stdout)
        selected = None
        for address in addresses[:_MAX_PROBES]:
            try:
                with socket.create_connection((address, port), timeout=2):
                    selected = address
                break
            except OSError:
                continue
        if selected is None:
            raise ValueError('No reachable public IPv6 address was discovered. ' + _FALLBACK)
        direct_options = ['-o', 'Hostname=' + selected, '-o', 'HostKeyAlias=' + identity,
                          '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none',
                          '-o', 'CheckHostIP=no', '-o', 'Port=' + str(port)]
        if settings.get('user'):
            direct_options += ['-o', 'User=' + _destination(settings['user'])]
    return ['ssh', '-N', *common, *direct_options, '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
            '-L', f'127.0.0.1:{local_port}:127.0.0.1:{remote_port}', destination]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Discover current direct IPv6 and open a local vision SSH tunnel.')
    parser.add_argument('target', nargs='?', help='Explicit SSH destination; bypasses discovery.')
    parser.add_argument('--print-command', action='store_true', help='Discover and print SSH argv without opening the tunnel.')
    parser.epilog = ('Environment: JETSON_SSH_TARGET, JETSON_DISCOVERY_HOST (jetson), '
                     'JETSON_KNOWN_HOSTS, LOCAL_PORT (3095), REMOTE_PORT (3090).')
    args = parser.parse_args(argv)
    try:
        command = prepare(args.target, os.environ)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.print_command:
        print(shlex.join(command))
        return 0
    local_port = _port(os.environ.get('LOCAL_PORT', '3095'))
    print(f'Connecting to {command[-1]} (not yet confirmed). After SSH connects, open http://127.0.0.1:{local_port}/\n'
          'Keep this terminal open; Ctrl-C closes the tunnel.', flush=True)
    os.execvp(command[0], command)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
