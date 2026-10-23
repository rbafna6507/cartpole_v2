"""Local preview credentials persist, stay private, and cannot execute jobs."""
import importlib
import json
import stat
from pathlib import Path


def dev_module():
    import cartpole_sdk.portal as portal
    assert (Path(portal.__file__).parent / 'dev.py').exists(), 'development launcher missing'
    return importlib.import_module('cartpole_sdk.portal.dev')


def test_credentials_are_private_distinct_role_secrets_and_persist(tmp_path):
    dev = dev_module()
    path, credentials = dev.prepare_credentials(tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert {principal[1] for principal in credentials.values()} == {'submit', 'operator'}
    assert len(credentials) == 2
    assert all(len(bytes.fromhex(token)) == 32 for token in credentials)
    original = path.read_bytes()
    assert dev.prepare_credentials(tmp_path) == (path, credentials)
    assert path.read_bytes() == original


def test_preview_binds_loopback_and_leaves_jobs_queued(tmp_path):
    dev = dev_module()
    server, path = dev.create_preview(tmp_path, port=0)
    try:
        assert server.server_address[0] == '127.0.0.1'
        job = server.store.submit('local-submitter', 'preview-test', b'def create_policy(): pass\n', 'policy.py', 'simulation', 1)
        assert server.store.get(job['id'])['status'] == 'pending'
        assert not any(role == 'worker' for _, role in server.credentials.values())
        assert json.loads(path.read_text()) == server.credentials
    finally:
        server.server_close()


def test_preview_metadata_contains_local_camera_but_no_secrets(tmp_path):
    from threading import Thread
    from urllib.request import urlopen
    dev = dev_module()
    server, _ = dev.create_preview(tmp_path, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/dev-info') as response:
            body = response.read().decode()
        assert json.loads(body) == {'local_preview': True, 'camera_url': 'http://127.0.0.1:3090'}
        assert all(token not in body for token in server.credentials)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
