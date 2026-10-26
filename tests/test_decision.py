"""T3: alarm decision and health limits. Run: python tests/test_decision.py"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "python"))
from decision import decide  # noqa: E402

N, H = datetime(2026, 10, 27, 6, 30), datetime(2026, 10, 27, 7, 0)
GOOD = {"score": 85, "confident": True}
RESTLESS = {"score": 55, "confident": True}
RAIN = {"detected": True, "confident": True}

CASES = [  # name, normal, hard, night, rain, shifted_yesterday, expected extra
    ("good night, no rain", N, H, GOOD, None, False, 0),
    ("restless night", N, H, RESTLESS, None, False, 15),
    ("restless + rain", N, H, RESTLESS, RAIN, False, 30),
    ("rain only", N, H, GOOD, RAIN, False, 15),
    ("slack only 10 min", N, datetime(2026, 10, 27, 6, 40), RESTLESS, RAIN, False, 10),
    ("shifted yesterday, score 55", N, H, RESTLESS, None, True, 0),
    ("shifted yesterday, score 35", N, H, {"score": 35, "confident": True}, None, True, 15),
    ("low-confidence night", N, H, {"score": 20, "confident": False}, None, False, 0),
    ("low-confidence rain", N, H, GOOD, {"detected": True, "confident": False}, False, 0),
    ("hard limit equal to normal", N, N, RESTLESS, RAIN, False, 0),
    ("hard limit already passed", N, datetime(2026, 10, 27, 6, 0), RESTLESS, RAIN, False, 0),
    ("very poor + rain, 60 min slack", N, datetime(2026, 10, 27, 7, 30), {"score": 10, "confident": True}, RAIN, False, 30),
]


def test_cases():
    for name, normal, hard, night, rain, shifted, want in CASES:
        rec = decide(normal, hard, night, rain, shifted)
        assert rec["extra_min"] == want, (name, rec)
        final = datetime.strptime(f"{rec['day']} {rec['final_alarm']}", "%Y-%m-%d %H:%M")
        assert final <= max(normal, hard) and rec["extra_min"] <= 30, (name, rec)
        assert rec["rules"] or want == 0, (name, rec)


if __name__ == "__main__":
    test_cases()
    for name, normal, hard, night, rain, shifted, want in CASES:
        print(f"{name:34} -> +{decide(normal, hard, night, rain, shifted)['extra_min']} (expected +{want})")
    print(f"T3: {len(CASES)}/{len(CASES)} pass")
