import hashlib,io,json,tarfile,subprocess
from pathlib import Path
import pytest


def bundle(path, *, name='test-release', member='README.md', content=b'ok', expected=None):
    manifest={'name':name,'git_commit':'a'*40,'files':{member:expected or hashlib.sha256(content).hexdigest()}}
    with tarfile.open(path,'w:gz') as t:
        for n,b in [('release-manifest.json',json.dumps(manifest).encode()),(member,content)]:
            m=tarfile.TarInfo(n);m.size=len(b);t.addfile(m,io.BytesIO(b))
    return path


def test_modified_bundle_rejected_before_install(tmp_path):
    from cartpole_sdk.release import unpack
    p=bundle(tmp_path/'bad.tar.gz',expected='0'*64)
    with pytest.raises(ValueError,match='hash'):unpack(p,tmp_path/'live')
    assert not (tmp_path/'live/releases/test-release').exists()


def test_traversal_rejected_without_outside_write(tmp_path):
    from cartpole_sdk.release import unpack
    p=bundle(tmp_path/'bad.tar.gz',member='../outside')
    with pytest.raises(ValueError):unpack(p,tmp_path/'live')
    assert not (tmp_path/'outside').exists()


def test_existing_release_is_never_overwritten(tmp_path):
    from cartpole_sdk.release import unpack
    p=bundle(tmp_path/'ok.tar.gz');target,manifest=unpack(p,tmp_path/'live')
    assert (target/'README.md').read_bytes()==b'ok'
    with pytest.raises(FileExistsError):unpack(p,tmp_path/'live')


def test_failed_dependency_install_preserves_active_release(tmp_path,monkeypatch):
    from cartpole_sdk.release import install
    root=tmp_path/'live';root.mkdir();old=root/'old';old.mkdir();(root/'active').symlink_to(old)
    p=bundle(tmp_path/'ok.tar.gz')
    def fail(*args,**kwargs):raise subprocess.CalledProcessError(1,args[0])
    monkeypatch.setattr(subprocess,'run',fail)
    with pytest.raises(subprocess.CalledProcessError):install(p,root,uv='uv',python='python3.11')
    assert (root/'active').resolve()==old


def test_activation_requires_verified_release_and_preserves_legacy_directory(tmp_path):
    from cartpole_sdk.release import activate
    root=tmp_path/'live';target=root/'releases/test-release';target.mkdir(parents=True)
    with pytest.raises(ValueError):activate(root,'test-release')
    (target/'release-ready.json').write_text('{}')
    (root/'active').mkdir()
    with pytest.raises(ValueError):activate(root,'test-release')
    assert (root/'active').is_dir() and not (root/'active').is_symlink()

@pytest.mark.parametrize('failure',['collision','write'])
def test_cli_launcher_failure_does_not_activate_new_release(tmp_path,monkeypatch,failure):
    from cartpole_sdk.release import main
    root=tmp_path/'live';root.mkdir();old=root/'old';old.mkdir();(root/'active').symlink_to(old)
    binaries=tmp_path/'bin';binaries.mkdir()
    if failure=='collision':(binaries/'cartpole').write_text('unrelated command')
    else:
        original=Path.write_text
        def fail_write(self,*args,**kwargs):
            if self==binaries/'cartpole-console':raise OSError('simulated write failure')
            return original(self,*args,**kwargs)
        monkeypatch.setattr(Path,'write_text',fail_write)
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:None)
    archive=bundle(tmp_path/'ok.tar.gz')
    with pytest.raises((ValueError,OSError)):
        main(['install','--archive',str(archive),'--root',str(root),'--bin-dir',str(binaries)])
    assert (root/'active').resolve()==old


def test_offline_actor_verification_exercises_numpy_backend(monkeypatch):
    import cartpole_sdk.release as release
    from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
    def broken(self,*args,**kwargs):raise RuntimeError('broken numpy binary')
    monkeypatch.setattr(NumpyActorBackend,'__init__',broken)
    with pytest.raises(RuntimeError,match='broken numpy binary'):
        release.verify_actors(Path(__file__).resolve().parents[1])
