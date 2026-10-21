"""Process-wide cyclic GC deferral is scoped, exception-safe and composable."""
import gc
import importlib
import threading

import pytest


def helper():
    return importlib.import_module('cartpole_sdk.rig.runtime').defer_cyclic_gc


@pytest.fixture(autouse=True)
def restore_gc_state():
    enabled=gc.isenabled()
    yield
    (gc.enable if enabled else gc.disable)()


@pytest.mark.parametrize('initially_enabled',[False,True])
def test_restores_original_gc_state_after_nested_scopes(initially_enabled):
    (gc.enable if initially_enabled else gc.disable)()
    with helper()():
        assert not gc.isenabled()
        with helper()():
            assert not gc.isenabled()
        assert not gc.isenabled()
    assert gc.isenabled() is initially_enabled


def test_exception_restores_gc_without_running_explicit_collection(monkeypatch):
    gc.enable()
    def forbidden(*args,**kwargs):
        pytest.fail('defer context must not explicitly collect, including on exit')
    monkeypatch.setattr(gc,'collect',forbidden)
    with pytest.raises(RuntimeError,match='operation failed'):
        with helper()():
            assert not gc.isenabled()
            raise RuntimeError('operation failed')
    assert gc.isenabled()


def test_overlapping_threads_keep_gc_disabled_until_last_scope_exits():
    gc.enable();entered=threading.Event();release=threading.Event();errors=[]
    def worker():
        try:
            with helper()():
                entered.set()
                if not release.wait(2):raise TimeoutError('test release timeout')
                if gc.isenabled():raise AssertionError('GC restored while scope still active')
        except BaseException as exc:
            errors.append(exc);entered.set()
    thread=threading.Thread(target=worker)
    try:
        with helper()():
            thread.start()
            assert entered.wait(2)
            assert not errors and not gc.isenabled()
        assert not gc.isenabled()
    finally:
        release.set()
        if thread.ident is not None:thread.join(2)
    assert not thread.is_alive() and not errors
    assert gc.isenabled()
