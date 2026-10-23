import pytest
from cartpole_sdk.portal import queue

def test_owner_bytes_count_distinct_hash_and_reject_before_write(tmp_path,monkeypatch):
    monkeypatch.setattr(queue,'MAX_OWNER_ARTIFACT_BYTES',8)
    store=queue.Store(tmp_path)
    store.submit('alice','one',b'x=1234','one.py','simulation',.1)
    store.submit('alice','same',b'x=1234','two.py','simulation',.1)
    before=set(store.blobs.iterdir())
    with pytest.raises(queue.QueueError,match='owner artifact quota'):store.submit('alice','new',b'x=2','new.py','simulation',.1)
    assert set(store.blobs.iterdir())==before
    store.submit('bob','one',b'x=2','new.py','simulation',.1)

def test_global_bytes_and_disk_reserve(tmp_path,monkeypatch):
    monkeypatch.setattr(queue,'MAX_STORE_ARTIFACT_BYTES',8)
    store=queue.Store(tmp_path)
    store.submit('alice','one',b'x=1234','one.py','simulation',.1)
    with pytest.raises(queue.QueueError,match='artifact storage quota'):store.submit('bob','two',b'x=2','two.py','simulation',.1)
    assert len(list(store.blobs.iterdir()))==1
    monkeypatch.setattr(queue,'MIN_FREE_DISK_BYTES',10**30)
    with pytest.raises(queue.QueueError,match='free disk'):store.submit('bob','three',b'x','three.py','simulation',.1)
    assert len(list(store.blobs.iterdir()))==1

def test_lifetime_job_limit(tmp_path,monkeypatch):
    monkeypatch.setattr(queue,'MAX_OWNER_JOBS',1)
    store=queue.Store(tmp_path)
    store.submit('alice','one',b'x','one.py','simulation',.1)
    with pytest.raises(queue.QueueError,match='owner lifetime job quota'):store.submit('alice','two',b'x','one.py','simulation',.1)
