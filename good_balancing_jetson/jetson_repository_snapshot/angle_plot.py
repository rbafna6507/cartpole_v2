"""Plot-only circular data helpers; recorded values and control are unchanged."""
import math


def angle_series(times, values, *, unwrap=False, period=2*math.pi, max_gap=.2):
    """Return plotting coordinates without false lines through a circular seam.

    unwrap accumulates shortest signed increments (motion must be less than half
    a turn between samples). Gaps/nonfinite samples start a new segment instead
    of inventing turn counts through missing data. All valid samples are kept.
    """
    if not math.isfinite(period) or period <= 0 or max_gap <= 0:
        raise ValueError('period and max_gap must be positive')
    if len(times) != len(values):
        raise ValueError('time and angle lengths must match')
    tx, yy = [], []
    previous_t = previous_value = continuous = None
    for t, value in zip(times, values):
        if not math.isfinite(t) or not math.isfinite(value):
            tx.append(math.nan); yy.append(math.nan)
            previous_t = previous_value = continuous = None
            continue
        new_segment = previous_t is None or t <= previous_t or t-previous_t > max_gap
        if new_segment:
            if tx:
                tx.append(math.nan); yy.append(math.nan)
            continuous = value
        else:
            difference = value-previous_value
            if unwrap:
                continuous += (difference+period/2) % period-period/2
            elif abs(difference) > period/2:
                tx.append(math.nan); yy.append(math.nan)
        tx.append(t); yy.append(continuous if unwrap else value)
        previous_t, previous_value = t, value
    return tx, yy
