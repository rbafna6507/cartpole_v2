"""Plot helper for cartpole.py; place this file beside cartpole.py.

Angles are radians. Wrap the display to [-pi, pi] and insert NaN breaks
at wrap boundaries so Matplotlib does not draw a false line through zero.
This transforms plot data only; it does not change telemetry or control.
No third-party dependencies.
"""
import math


def angle_series(times, angles, *, unwrap=False, period=2*math.pi, max_gap=.2):
    """Return (plot_times, plot_angles) for Matplotlib's set_data().

    Inputs must have equal lengths. Nonfinite samples and non-increasing
    timestamps and long gaps break the line. Neither input is modified.
    Optional unwrapping supports the archived encoder-analysis tools; it never
    infers rotation across a gap or reset. ``period`` is in the input units.
    """
    times = list(times)
    angles = list(angles)
    if len(times) != len(angles):
        raise ValueError('times and angles must have the same length')
    if not math.isfinite(period) or period <= 0 or not math.isfinite(max_gap) or max_gap <= 0:
        raise ValueError('period and max_gap must be finite and positive')
    plot_times, plot_angles = [], []
    previous = None
    for t, angle in zip(times, angles):
        t, angle = float(t), float(angle)
        if not (math.isfinite(t) and math.isfinite(angle)):
            plot_times.append(t)
            plot_angles.append(math.nan)
            previous = None
            continue
        half = period/2
        wrapped = angle if -half <= angle <= half else (angle+half) % period-half
        new_segment = previous is None or t <= previous[0] or t-previous[0] > max_gap
        if unwrap:
            value = angle if new_segment else previous[3] + (angle-previous[2]+half) % period-half
        else:
            value = wrapped
        if previous is not None:
            if new_segment or (not unwrap and abs(wrapped - previous[1]) > half):
                plot_times.append(math.nan)
                plot_angles.append(math.nan)
        plot_times.append(t)
        plot_angles.append(value)
        previous = (t, wrapped, angle, value)
    return plot_times, plot_angles
