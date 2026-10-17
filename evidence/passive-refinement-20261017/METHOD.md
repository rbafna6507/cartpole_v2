# Passive refinement implementation plan and pre-fit method

> For agentic workers: execute inline. User requested autonomous completion, no additional subagents, no production edits, and no commits.

**Goal:** Determine whether newly authorized training recordings justify a defensible improvement to the frozen batch-6 passive model for development Gym/RL.

**Architecture:** Preserve the original four-parameter smooth friction law and baseline. Fit bounded candidates using only existing batch-6 development records and training8/training9. Select and freeze one candidate using training-only criteria before reading validation8/validation9 measurements in this experiment. Those validation recordings were previously inspected and are regression holdouts, not novel blind validation.

**Tech stack:** Python 3.11, NumPy, SciPy 1.16.3, Matplotlib. Reuse frozen DOP853 dynamics and analytical sensitivities.

**Spec:** Parent task instruction received 2026-10-17; scope exclusively this evidence directory and ignored runs outputs.

## Fixed decisions recorded before fitting

- Use both batch-6 recordings (19 releases, already development in the baseline freeze) and training8/training9 (24 releases) without dropping any annotated release. Preserve the distinction between historical development labels and present fit role.
- Do not fit validation8 or validation9, change annotations, change their quality gates, discard high residual releases, reinterpret camera disagreement as ground truth, or correct raw measurements.
- Preserve baseline coefficients `[60.806177009128575, 0.006891975341585199, 6.898766153634008, 1.6268943123178277]` and its causal `history_rawq` initializer.
- Dynamics: `q'' = a*sin(q) + b*cos(q) - gamma*q' - c*tanh(q'/0.05)`. Four fitted coefficients only; no low-speed extension, angular remapping, per-recording phase or delay.
- Compare pooled weak least squares, pooled robust weak fit, and robust full-trajectory fit. Weak windows use the existing 0.35 s matrix and physical bounds; robust loss is soft-L1 with scale `0.1*std(training weak targets)`. Full-trajectory loss uses every fifth sample plus final sample, equal total release weight, soft-L1 with 0.03 rad residual scale, analytic sensitivities, and bounded per-release initial states as training nuisance parameters only.
- Compare the frozen initializer with one fixed robust causal history initializer: soft-L1 0.02 rad state fit over available preceding history, returning its fitted end state. No future samples, per-release choice, or history-length tuning. Short forecasts use up to 0.2 s history and 0.5 s forecast; continuous uses both 0.25 s and 0.5 s, with 0.5 s primary. Initial-history samples are excluded from scoring.
- The baseline coefficients with the new initializer are an explicit candidate, so initialization improvements cannot be mislabeled coefficient improvements.
- Selection score: equal-recording mean continuous 0.5 s RMS. A candidate must improve this score at least 5%, not increase equal-recording mean short RMS by more than 2%, retain every short numeric and coverage gate that baseline passes, not worsen any recording's continuous 0.5 s RMS by more than 10%, and not increase equal-recording mean continuous 0.25 s RMS by more than 5%. Among eligible candidates select lowest primary score. Otherwise retain baseline.
- Candidate fitting and selection are exploratory training evidence. Report leave-one-recording-out robust-weak coefficient ranges as a limited stability diagnostic, not an uncertainty confidence interval. Report paired release bootstrap intervals for regression error changes as descriptive conditional uncertainty, not novel validation.
- Freeze exact coefficients, initializer, training source/annotation hashes, method hashes and selection results before validation scoring. No tuning after regression scoring.
- Recommendation after regression: improvement must retain baseline passing short gates, improve pooled continuous 0.5 s RMS at least 5%, not worsen either validation recording's primary RMS by more than 10%, and not increase pooled short or continuous 0.25 s RMS more than 5%. A failed regression criterion means retain baseline; no second candidate is selected from validation.
- Retain every existing camera/pose failure. Development-only regardless of prediction gains; this work does not identify driven-cart parameters, certify cart restraint, calibrate absolute angles, or authorize hardware.

## Files and execution

- [ ] `tools/refine.py`: training-only loading, fits, causal scoring, training selection, freeze, regression scoring, full per-release residuals and hashes.
- [ ] `tools/report.py`: pooled metrics, uncertainty, plots, Markdown report and verification.
- [ ] Preserve `training.json.gz`, `candidate-freeze.json`, `regression.json.gz`, concise summaries and source hashes; scripts refuse overwrite.
- [ ] Verify analytic sensitivity numerically, baseline scoring parity against preserved baseline summaries, no skipped releases, matching sample counts, hash separation, preserved gate failures and frozen method hashes.
- [ ] Visually inspect plots and report practical limits.

## Review focus

Causal initializers must never see forecast samples. Validation labels must never enter fitting. Full-trajectory nuisance initial states must never enter evaluation. Partial final releases and camera failures remain scored. Raw source and annotation hashes must bind every row.
