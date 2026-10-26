"""Rain from microphone feature rows (spec F7). Rule first; a classifier once enough labelled minutes exist."""
import statistics

import predictor

# Rule thresholds: calibration knobs, set from labelled minutes (test T8).
FLAT_MIN = 300          # spectral flatness x1000: rain is broadband
HIGH_BAND_MIN = -600    # 4-7.8 kHz band, dB x10
RMS_STD_MAX = 30        # dB x10 over the minute: rain is steady
IMPULSE_RANGE = (20, 400)  # impulses per block x100: drops, not silence and not speech
MIN_MINUTES = 30        # minutes with mic data in the last hour for a confident answer
RAIN_SHARE = 0.5        # share of those minutes that must look like rain
MIN_LABELS = 20         # per class, before the classifier replaces the rule


def minutes(rows):
    """Groups 1 s rows into minute feature vectors."""
    by = {}
    for r in rows:
        if r["blocks"]:
            by.setdefault(int(r["ts"] // 60), []).append(r)
    out = []
    for m, rs in sorted(by.items()):
        if len(rs) < 20:
            continue
        mean = lambda k: statistics.fmean(x[k] for x in rs)
        out.append({"minute": m, "x": [mean("rms"), mean("b1"), mean("b2"), mean("b3"), mean("b4"),
                                        mean("flat"), mean("imp"), statistics.pstdev(x["rms"] for x in rs)]})
    return out


def rule(x):
    rms, b1, b2, b3, b4, flat, imp, rms_std = x
    return flat >= FLAT_MIN and b4 >= HIGH_BAND_MIN and rms_std <= RMS_STD_MAX and \
        IMPULSE_RANGE[0] <= imp <= IMPULSE_RANGE[1]


def detect(rows, labelled):
    """rows: mic rows of the last 60 min. labelled: list of (x, is_rain).

    Returns {"detected", "confident", "minutes", "rain_minutes", "method"}.
    """
    mins = minutes(rows)
    pos = sum(1 for _, y in labelled if y)
    method = "rule"
    if pos >= MIN_LABELS and len(labelled) - pos >= MIN_LABELS and mins:
        model = predictor.fit([x for x, _ in labelled], [int(y) for _, y in labelled], quick=True)
        flags = [p >= 0.5 for p in predictor.p_true(model, [m["x"] for m in mins])]
        method = "logistic"
    else:
        flags = [rule(m["x"]) for m in mins]
    n, k = len(mins), sum(flags)
    return {"detected": n > 0 and k / n >= RAIN_SHARE, "confident": n >= MIN_MINUTES,
            "minutes": n, "rain_minutes": k, "method": method}
