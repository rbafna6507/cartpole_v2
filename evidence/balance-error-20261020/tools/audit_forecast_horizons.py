#!/usr/bin/env python3
"""Rescore saved conditional predictions; never fit or integrate a model.

Run from the repository root. The destination must not already exist.
"""

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path


HORIZONS_MS = (10, 50, 100, 200, 500)
INITIALIZERS = ("causal_encoder", "recorded_omega")
TIME_TOLERANCE_S = 1e-8


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate_source(document, source_bytes):
    if sha256(source_bytes) != document["analysis_source_sha256"]:
        raise ValueError("frozen analysis source hash does not match saved predictions")


def metrics(errors):
    if not errors or not all(math.isfinite(e) for e in errors):
        raise ValueError("missing or nonfinite residuals")
    rms = math.sqrt(math.fsum(e * e for e in errors) / len(errors))
    return {"sample_count": len(errors), "rmse_rad": rms, "rmse_deg": math.degrees(rms)}


def audit_windows(windows):
    selected = [w for w in windows if w["points"] and
                all(p["phase"] == "native_mode_3" for p in w["points"])]
    if not selected:
        raise ValueError("no wholly-balance prediction windows")
    result = {
        "source_window_count": len(windows),
        "selected_window_count": len(selected),
        "excluded_mixed_or_other_phase_windows": len(windows) - len(selected),
        "origins": [{k: w[k] for k in ("start_s", "end_s", "initial_encoder_angle_rad",
                     "causal_initial_omega_rad_s", "recorded_initial_omega_rad_s")}
                    for w in selected],
        "initial_rate_difference": metrics([
            w["causal_initial_omega_rad_s"] - w["recorded_initial_omega_rad_s"]
            for w in selected]),
        "initializers": {},
    }
    # Rate difference uses the same numerical RMS but has rate units, not angles.
    rate = result.pop("initial_rate_difference")
    result["initial_rate_difference_rms_rad_s"] = rate["rmse_rad"]
    for name in INITIALIZERS:
        exact = {str(h): [] for h in HORIZONS_MS}
        prefix = {str(h): [] for h in HORIZONS_MS}
        for w in selected:
            points = w["points"]
            leads = [p["t_s"] - w["start_s"] for p in points]
            if any(not math.isfinite(t) or t <= 0 for t in leads) or any(
                    b <= a for a, b in zip(leads, leads[1:])):
                raise ValueError("forecast times must be finite, positive and increasing")
            errors = []
            for p in points:
                delta = p[name + "_prediction_rad"] - p["measured_encoder_rad"]
                recomputed = math.atan2(math.sin(delta), math.cos(delta))
                error = p[name + "_error_rad"]
                if not math.isfinite(error) or abs(recomputed - error) > 1e-9:
                    raise ValueError("saved circular residual does not match prediction")
                errors.append(error)
            for h in HORIZONS_MS:
                target = h / 1000
                matches = [i for i, t in enumerate(leads) if abs(t - target) <= TIME_TOLERANCE_S]
                if len(matches) != 1:
                    raise ValueError(f"expected one exact lead at {h}ms for origin {w['start_s']}")
                exact[str(h)].append(errors[matches[0]])
                prefix[str(h)].extend(e for t, e in zip(leads, errors)
                                      if t <= target + TIME_TOLERANCE_S)
        result["initializers"][name] = {
            "exact_lead": {h: metrics(e) for h, e in exact.items()},
            "pooled_prefix": {h: metrics(e) for h, e in prefix.items()},
        }
    return result


def build_report(document, input_path, input_bytes, source_path, source_bytes):
    validate_source(document, source_bytes)
    trials = []
    for run in document["validation"]:
        if run["declared_dataset_role"] != "validation":
            raise ValueError("validation dataset role mismatch")
        for trial in run["trials"]:
            if trial["kind"] != "coupled" or not trial["completed"] or trial["status"] != "scored":
                continue
            baseline = trial["phase_baselines"]["firmware_reference"]
            if baseline["phase_offset_rad"] != 0.0:
                raise ValueError("expected unchanged zero-phase firmware reference")
            scores = baseline["scores"]
            trials.append({
                "run": run["name"], "trial": trial["id"], "dataset_role": "validation",
                "campaign_completed": run["campaign_completed"], "sensor_mode": run["sensor_mode"],
                "inherited_source_hashes": {k: run[k] for k in (
                    "source_manifest_sha256", "source_raw_sha256", "source_report_sha256")},
                "baseline": "firmware_reference", "phase_offset_rad": baseline["phase_offset_rad"],
                "original_forecast_checks_pass": scores["forecast_checks_pass"],
                "original_forecast_check_reasons": scores["forecast_check_reasons"],
                **audit_windows(scores["windows"]),
            })
    if not trials:
        raise ValueError("no completed scored validation coupled trials")
    return {
        "schema": "cartpole-saved-forecast-horizon-audit-v1",
        "provenance": {
            "input_analysis_path": str(input_path), "input_analysis_sha256": sha256(input_bytes),
            "frozen_analysis_source_path": str(source_path),
            "frozen_analysis_source_sha256": sha256(source_bytes),
            "audit_script_sha256": sha256(Path(__file__).read_bytes()),
            "python_version": platform.python_version(),
            "source_hash_verification": "analysis and analysis-source bytes hashed here; raw/manifest/report hashes inherited from bound analysis, not independently re-read",
        },
        "frozen_model": document["frozen_model"],
        "frozen_model_sha256": document["frozen_model_sha256"],
        "model_law": document["model_law"],
        "parameters_fitted": False, "model_reintegrated": False,
        "phase_selected_from_scores": False, "hardware_accepted": False,
        "recommended_model": None, "physical_acceleration_measured": False,
        "global_encoder_phase_calibrated": False,
        "horizons_ms": list(HORIZONS_MS), "exact_lead_tolerance_s": TIME_TOLERANCE_S,
        "selection": "Existing nonoverlapping 0.5s windows with every saved prediction point labelled native_mode_3. Same windows/origins for every horizon and both initializers; no residual-based selection. Origin phase itself is not separately stored in this prediction artifact.",
        "scope": "Completed scored coupled validation trials only; training/development roles are not pooled or relabelled.",
        "definitions": {
            "exact_lead": "One saved circular angle residual per origin at precisely the requested lead (within tolerance); no interpolation.",
            "pooled_prefix": "All saved circular angle residuals with 0 < lead <= requested horizon, pooled across the same origins. The zero-error initialized point is excluded.",
            "causal_encoder": "Original primary: quadratic endpoint derivative of seven past/current encoder samples.",
            "recorded_omega": "Original comparator: current filtered firmware omega; not an independently measured angular-rate truth.",
        },
        "source_limitations": document["limitations"],
        "audit_limitations": [
            "Post-hoc diagnostic of previously inspected validation data; no new holdout, model selection, fit, calibration, or acceptance test.",
            "This is conditional replay of recorded closed-loop command acceleration, not independent physical acceleration or closed-loop simulated feedback.",
            "Upright instability can amplify initialization and input/model discrepancy over 0.5s. This audit does not identify their separate contributions.",
            "Shorter lead errors and initializer sensitivity do not establish actuator calibration or hardware suitability; original failed forecast checks remain failed.",
            "The wholly-balance window subset differs slightly from the original pool of all points labelled balance, which can include phase-crossing windows.",
            "Circular residuals are bounded by pi; long-horizon error is not an unwrapped rotation error. Overlapping prefix scores are correlated, not independent experiments.",
        ],
        "trials": trials,
    }


def write_plot(report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report["provenance"]["matplotlib_version"] = matplotlib.__version__
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.5), sharey=True)
    colors = {"causal_encoder": "#1565c0", "recorded_omega": "#c65d13"}
    labels = {"causal_encoder": "Causal encoder rate", "recorded_omega": "Firmware rate"}
    for ax, metric, title in zip(axes, ("exact_lead", "pooled_prefix"),
                                 ("Exact lead: one residual per origin", "Pooled prefix: all residuals up to lead")):
        for i, trial in enumerate(report["trials"]):
            for name in INITIALIZERS:
                ax.plot(HORIZONS_MS, [trial["initializers"][name][metric][str(h)]["rmse_deg"]
                                     for h in HORIZONS_MS], marker="o", color=colors[name],
                        linestyle=("-", "--", ":", "-.")[i % 4],
                        label=f"{labels[name]}, trial {trial['trial'].split('-')[0]}")
        ax.set_xscale("log")
        ax.set_xticks(HORIZONS_MS, [str(h) for h in HORIZONS_MS])
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Forecast lead / prefix horizon (ms)")
        ax.grid(alpha=0.2)
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel("Circular angle RMSE (degrees)")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Recorded-command conditional forecasts near upright", fontsize=13)
    fig.text(0.5, 0.015, "Same 44 wholly-balance windows per trial; fixed phase = 0; saved predictions only. No physical actuator validation.",
             ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.045, 1, 0.95))
    fig.savefig(output / "horizons.png", dpi=170)
    plt.close(fig)


def write_readme(report, output, args):
    text = ["# Saved-forecast horizon audit", "",
            "The large 0.5-second error is a conditional forecast-pipeline result. It does not isolate physical plant-model error. These saved predictions show substantial horizon amplification and sensitivity to the initial angular-rate estimate, with no new fitting or simulation.", "",
            "Both validation trials retain exactly the same 44 original windows at all five horizons and for both initializers. Every saved point in those windows is labelled native balance mode. Exact-lead scores use 44 residuals each; prefix scores use 44, 220, 440, 880 and 2,200 residuals at 10, 50, 100, 200 and 500 ms. Initial zero-error points are excluded.", "",
            "| Trial | Initial rate | Metric | 10 ms | 50 ms | 100 ms | 200 ms | 500 ms |",
            "|---|---|---|---:|---:|---:|---:|---:|"]
    for t in report["trials"]:
        for name in INITIALIZERS:
            for metric in ("exact_lead", "pooled_prefix"):
                values = " | ".join(f"{t['initializers'][name][metric][str(h)]['rmse_deg']:.3f}°" for h in HORIZONS_MS)
                text.append(f"| {t['trial']} | {name} | {metric} | {values} |")
    text.extend(["", "The 500 ms causal prefix RMS is approximately 73–75°, while the exact 500 ms lead is 106–112°. At 10 ms both initializers are approximately 1.2–1.5°. Using firmware rate lowers the 500 ms prefix RMS to approximately 47–49°, yet exact 500 ms errors remain 103–105°. This establishes sensitivity, not that firmware rate is ground truth or that initialization explains all discrepancy.", "",
                 "The upright gravitational term amplifies departures. Recorded control actions depend on the real rig state; the diverging open-loop forecast never receives corrective actions based on its own predicted state. Differences can therefore combine initial angle/rate, phase, commanded-versus-physical acceleration, input reconstruction/delay, and model mismatch. No evident sign/unit/wrap defect was identified in the accompanying read-only review; these scores alone cannot rule one out or assign a causal share.", "",
                 "The existing forecast API is fixed at 0.5 seconds. Its saved points already support this shorter-horizon diagnostic. No frozen implementation, source prediction, raw dataset, or validation role was changed. The original forecast checks remain failed and hardware acceptance remains false.", "",
                 "## Limitations", ""])
    text.extend("- " + item for item in report["source_limitations"] + report["audit_limitations"])
    text.extend(["", "## Reproduce", "", "Run from the repository root into a new output directory:", "", "```sh",
                 "MPLCONFIGDIR=/tmp/cartpole-horizon-mpl .venv/bin/python " + str(Path(__file__).resolve()) + " \\",
                 f"  --input {args.input} \\", f"  --analysis-source {args.analysis_source} \\",
                 "  --output /tmp/cartpole-horizon-audit-reproduction", "```", "",
                 "`report.json` binds this script, input analysis, original analysis source, and model to SHA-256 hashes. Original raw/manifest/report hashes are preserved as inherited provenance; this script does not reread those raw inputs. The script refuses an existing output directory, checks the frozen analysis-source hash, checks saved residuals against predictions, and rejects missing exact leads rather than interpolating.", ""])
    (output / "README.md").write_text("\n".join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--analysis-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output directory already exists; choose a new destination")
    raw, source = args.input.read_bytes(), args.analysis_source.read_bytes()
    report = build_report(json.loads(raw), args.input, raw, args.analysis_source, source)
    args.output.mkdir(parents=True, exist_ok=False)
    write_plot(report, args.output)
    write_readme(report, args.output, args)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "trial_count": len(report["trials"]),
                      "origins_per_trial": [t["selected_window_count"] for t in report["trials"]]}))


if __name__ == "__main__":
    main()
