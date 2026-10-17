#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "scipy==1.16.3"]
# ///
"""Synthetic verification of initializer causality and analytic derivatives."""
import argparse,json
from pathlib import Path
import numpy as np
import refine

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=np.linspace(0,1,251);q=refine.ode_solution(t,[3.7,-.2],refine.BASELINE)[0]
    rows=[]
    for method in ['frozen_rawq','robust_history']:
        for duration in [.2,.25,.5]:
            i=int(np.searchsorted(t,.6));original=refine.state(t,q,i,refine.BASELINE,method,duration)
            damaged=q.copy();damaged[i+1:]=100+np.arange(len(q)-i-1)
            mutated=refine.state(t,damaged,i,refine.BASELINE,method,duration)
            delta=float(np.max(abs(original-mutated)));assert delta==0
            assert np.max(abs(original-refine.ode_solution(t,[3.7,-.2],refine.BASELINE)[:,i]))<2e-5
            rows.append(dict(method=method,history_s=duration,future_mutation_max_state_change=delta,passed=True))
    out=dict(passed=True,causality=rows,analytic_sensitivity=refine.signature_check(),method_sha256=refine.sha(Path(refine.__file__)))
    refine.write(a.output,out);print(json.dumps(out,indent=2))
if __name__=='__main__':main()
