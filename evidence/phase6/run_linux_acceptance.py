from pathlib import Path
import hashlib,json,platform,sys,unittest
root=Path.cwd()
manifest=json.loads((root/'release-source-manifest.json').read_text())
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in manifest.items())
print('RELEASE_SOURCE_HASHES_VERIFIED',len(manifest),flush=True)
print('RUNTIME',platform.platform(),sys.version,flush=True)
sys.path.insert(0,str(root/'tests'))
import test_portal_worker
original=test_portal_worker.run_once
results=[]
def record(*args,**kwargs):
 result=original(*args,**kwargs)
 if result and result.get('result',{}).get('simulation_time_ns')==10_000_000_000:
  results.append(result)
  print('LEARNED_QUEUE_RESULT',json.dumps(result,sort_keys=True),flush=True)
 return result
test_portal_worker.run_once=record
suite=unittest.defaultTestLoader.discover('tests',pattern='test_portal*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
(root/'linux-acceptance-result.json').write_text(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'skips':[(str(t),r) for t,r in result.skipped],'learned_results':results,'source_manifest_sha256':hashlib.sha256((root/'release-source-manifest.json').read_bytes()).hexdigest()},indent=2)+'\n')
raise SystemExit(0 if result.wasSuccessful() else 1)
