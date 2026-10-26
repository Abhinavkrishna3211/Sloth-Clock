"""Validator checks for the wake message (part of T4). Run: python tests/test_validator.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "python"))
from validator import validate  # noqa: E402

REC = {"normal_alarm": "06:30", "final_alarm": "06:45", "hard_limit": "07:00", "extra_min": 15,
       "night": {"score": 52, "confident": True, "minutes": 420}}
RANGE = {**REC, "night": {**REC["night"], "awake_from": "02:10", "awake_to": "03:30"}}

CASES = [  # text, record, should pass
    ("Good morning! Night score 52, so you got 15 extra minutes. Up at 6:45.", REC, True),
    ("Rise at 06:45 am, fifteen minutes later than usual.", REC, True),
    ("Up at 6.45, alarm moved from 6:30.", REC, True),
    ("Up at 18:45.", REC, False),
    ("Up at 6:45 pm.", REC, False),
    ("Good morning, up at 7:15.", REC, False),
    ("You got 20 extra minutes.", REC, False),
    ("You got twenty extra minutes.", REC, False),
    ("Sleep a little longer, just half an hour more.", REC, False),
    ("Press snooze if you like.", REC, False),
    ("You were restless 2:10–3:30, up at 6:45.", RANGE, True),
    ("You were restless 2:10-3:30, up at 6:45.", RANGE, True),
    ("Score 52 of 100.", REC, False),
    ("Take one tiny step today. Up at 6:45.", REC, True),
    ("Good morning, the sun is up.", REC, False),  # must say the alarm time
    ("Up at 6:45, it is a bit chilly.", REC, False),  # weather without rain data
    ("Up at 6:45, the rain is soft.", {**REC, "rain": {"detected": True, "confident": True}}, True),
    ("Up at 6:30, I gave you a little extra time.", {**REC, "extra_min": 0, "final_alarm": "06:30"}, False),
    ("Up at 6:30, no extra time today.", {**REC, "extra_min": 0, "final_alarm": "06:30"}, True),
    ("", REC, False),
]


def test_cases():
    for text, rec, want in CASES:
        ok, why = validate(text, rec, need_time=True)
        assert ok == want, (text, why)


def test_time_optional():
    assert validate("Morning, sleepyhead. You had a rough night.", REC)[0]
    assert not validate("Morning, sleepyhead. Up at 7:15.", REC)[0]


if __name__ == "__main__":
    test_time_optional()
    test_cases()
    print(f"validator: {len(CASES)}/{len(CASES)} pass")
