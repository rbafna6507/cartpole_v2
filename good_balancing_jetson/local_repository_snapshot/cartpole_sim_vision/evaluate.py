import argparse,json
from pathlib import Path
from evaluate_policy import evaluate,animate
p=argparse.ArgumentParser();p.add_argument('policy');p.add_argument('--episodes',type=int,default=30);p.add_argument('--html',action='store_true');a=p.parse_args()
if a.episodes<1:p.error('episodes must be positive')
summary,trace=evaluate(a.policy,a.episodes);print(json.dumps(summary,indent=2))
if a.html:
 cfg=json.load(open(a.policy+'_config.json'))
 animation=animate(trace,length=cfg.get('link_length',.125),stop=cfg.get('rail_limit',.2)-.02)
 Path(a.policy+'_replay.html').write_text(animation.to_jshtml())
