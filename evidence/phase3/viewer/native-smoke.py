import faulthandler
faulthandler.dump_traceback_later(5,exit=True)
from cartpole_sdk.sim.viewer import run_viewer
run_viewer(duration=.5)
faulthandler.cancel_dump_traceback_later()
print('GUI_COMPLETED',flush=True)
