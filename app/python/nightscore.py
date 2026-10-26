"""Night score (spec F1): explainable, from the 10 s radar rows."""
from statistics import pstdev

import config as C


def night_score(rows, start, end, min_minutes):
    """rows: dicts with ts, presence, breath, move_max. start/end: unix seconds."""
    total_min = max(1, int((end - start) // 60))
    by_min = {}
    for r in rows:
        m = int((r["ts"] - start) // 60)
        if 0 <= m < total_min:
            by_min.setdefault(m, []).append(r)

    restless = irregular = in_bed = 0
    long_awakenings, run = 0, 0
    breaths = {}
    for m in range(total_min):
        rs = by_min.get(m)
        if not rs:
            run = 0  # no data: cannot call it an awakening
            continue
        present = [r for r in rs if r["presence"] >= C.PRESENT_PCT]
        moving = [r for r in rs if r["move_max"] >= C.MOVE_THRESHOLD]
        if moving or 0 < len(present) < len(rs):  # movement, or presence lost then regained
            restless += 1
        if len(present) * 2 >= len(rs):
            in_bed += 1
        breaths[m] = [r["breath"] for r in present if r["breath"] > 0]
        window = breaths.get(m - 1, []) + breaths[m]  # last 2 minutes
        if len(window) >= 6 and pstdev(window) > C.BREATH_STD_THRESHOLD:
            irregular += 1
        awake = len(present) * 2 < len(rs) or len(moving) == len(rs)
        run = run + 1 if awake else 0
        if run == C.LONG_AWAKE_MIN:
            long_awakenings += 1

    observed = len(by_min)
    pct = lambda n: 100.0 * n / observed if observed else 0.0
    score = 100 - (C.W_RESTLESS * pct(restless) + C.W_IRREGULAR * pct(irregular)
                   + C.W_LONG_AWAKE * long_awakenings)
    coverage = sum(1 for r in rows if start <= r["ts"] < end) / (total_min * 6)
    confident = (observed >= min_minutes and coverage >= C.MIN_COVERAGE
                 and in_bed * 2 >= observed)
    return {
        "score": int(round(min(100, max(0, score)))),
        "minutes": observed,
        "restless_min": restless,
        "irregular_min": irregular,
        "long_awakenings": long_awakenings,
        "coverage_pct": int(round(coverage * 100)),
        "confident": confident,
    }
