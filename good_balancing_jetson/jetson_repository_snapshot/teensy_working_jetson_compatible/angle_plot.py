"""Plot helper for cartpole.py; place this file beside cartpole.py.

Angles are radians. Wrap the display to [-pi, pi] and insert NaN breaks
at wrap boundaries so Matplotlib does not draw a false line through zero.
This transforms plot data only; it does not change telemetry or control.
No third-party dependencies.
"""
import math


def angle_series(times, angles):
    """Return (plot_times, plot_angles) for Matplotlib's set_data().

    Inputs must have equal lengths. Nonfinite samples and non-increasing
    timestamps break the line. Neither input is modified.
    """
    times = list(times)
    angles = list(angles)
    if len(times) != len(angles):
        raise ValueError('times and angles must have the same length')
    plot_times, plot_angles = [], []
    previous = None
    for t, angle in zip(times, angles):
        t, angle = float(t), float(angle)
        if not (math.isfinite(t) and math.isfinite(angle)):
            plot_times.append(t)
            plot_angles.append(math.nan)
            previous = None
            continue
        wrapped = math.atan2(math.sin(angle), math.cos(angle))
        if previous is not None:
            previous_t, previous_angle = previous
            if t <= previous_t or abs(wrapped - previous_angle) > math.pi:
                plot_times.append(math.nan)
                plot_angles.append(math.nan)
        plot_times.append(t)
        plot_angles.append(wrapped)
        previous = (t, wrapped)
    return plot_times, plot_angles
