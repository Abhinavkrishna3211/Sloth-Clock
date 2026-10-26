"""Tiny-step engine, predictor and rain rule (T6-T8 logic). Run: python tests/test_steps_rain.py"""
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "python"))
import card  # noqa: E402
import predictor  # noqa: E402
import rain  # noqa: E402
import tasks  # noqa: E402

TODAY = date(2026, 10, 26)


def test_countdown():
    assert tasks.countdown(date(2026, 10, 26), TODAY) == "Today"
    assert tasks.countdown(date(2026, 10, 27), TODAY) == "Tomorrow"
    assert tasks.countdown(date(2026, 11, 2), TODAY) == "In 7 days"
    assert tasks.countdown(date(2026, 10, 24), TODAY) == "2 days ago"
    items = [{"title": "a", "due": "2026-11-05", "done": 0}, {"title": "b", "due": "2026-10-28", "done": 0},
             {"title": "c", "due": "2026-10-01", "done": 0}, {"title": "d", "due": "2026-10-27", "done": 1},
             {"title": "e", "due": "", "done": 0}]
    assert [i["title"] for i in tasks.upcoming(items, TODAY)] == ["b", "a"]


def test_steps_ok():
    good = {"tiny": "Open the tax folder.", "small": "Sort 5 receipts.", "normal": "Fill page 2 of form 16."}
    assert tasks.steps_ok(good, "File form 16")[0] is False  # 2 is not in the title
    good["normal"] = "Fill the first page of form 16."
    assert tasks.steps_ok(good, "File form 16")[0]
    assert not tasks.steps_ok({"tiny": "x", "small": "y"}, "t")[0]
    assert not tasks.steps_ok({"tiny": "", "small": "y", "normal": "z"}, "t")[0]
    assert tasks.steps_ok(tasks.fallback_steps("Clean garage"), "Clean garage")[0]


def test_cold_start():
    f = lambda score: (lambda s: [score, 0, -1, tasks.SIZES.index(s), 0, 6, 0])
    assert tasks.choose_size([], f(80))[0] == "small"
    assert tasks.choose_size([], f(50))[0] == "tiny"
    assert tasks.choose_size([([1] * 7, 1)] * 19, f(90))[0] == "small"  # never normal before 20 rows


def test_predictor():
    # Synthetic only: done when the night was good and the step was small. Checks the plumbing, not accuracy.
    rnd = random.Random(1)
    hist = []
    for _ in range(60):
        score, size = rnd.randint(20, 95), rnd.randint(0, 2)
        hist.append(([score, rnd.randint(0, 6), -1, size, 0.5, 6, 0], int(score - 25 * size > 45)))
    good = lambda s: [90, 2, -1, tasks.SIZES.index(s), 0.5, 6, 0]
    bad = lambda s: [25, 2, -1, tasks.SIZES.index(s), 0.5, 6, 0]
    s_good, info = tasks.choose_size(hist, good)
    s_bad, _ = tasks.choose_size(hist, bad)
    assert info["method"] == predictor.BACKEND
    assert tasks.SIZES.index(s_good) > tasks.SIZES.index(s_bad) and s_bad == "tiny", (s_good, s_bad, info)
    assert predictor.fit([[1], [2]], [1, 1]) is None
    assert tasks.choose_size([([1] * 7, 1)] * 25, good)[0] == "tiny"  # one outcome only: stay tiny


def rows(minute, n, rms, b4, flat, imp, jitter=0):
    return [{"ts": minute * 60 + s, "blocks": 8, "rms": rms + (jitter if s % 2 else -jitter), "b1": -300,
             "b2": -400, "b3": -500, "b4": b4, "flat": flat, "imp": imp} for s in range(n)]


def test_rain():
    rainy = [r for m in range(40) for r in rows(m, 50, -350, -500, 450, 80)]
    quiet = [r for m in range(40) for r in rows(m, 50, -700, -800, 150, 0)]
    speech = [r for m in range(40) for r in rows(m, 50, -300, -550, 350, 80, jitter=60)]
    assert rain.detect(rainy, []) == {"detected": True, "confident": True, "minutes": 40,
                                      "rain_minutes": 40, "method": "rule"}
    assert not rain.detect(quiet, [])["detected"]
    assert not rain.detect(speech, [])["detected"]
    few = rain.detect(rainy[:10 * 50], [])
    assert few["detected"] and not few["confident"]
    assert rain.detect(rows(0, 10, -350, -500, 450, 80), [])["minutes"] == 0  # under 20 rows: not a minute
    labelled = [(m["x"], True) for m in rain.minutes(rainy)[:25]] + [(m["x"], False) for m in rain.minutes(quiet)[:25]]
    r = rain.detect(rainy, labelled)
    assert r["method"] == "logistic" and r["detected"]  # rain stays fast: it is in the alarm decision


def test_month():
    m = card.month(TODAY, [date(2026, 10, 29), date(2026, 11, 2), date(2026, 10, 29)])
    assert m == {"title": "October 2026", "first": 3, "days": 31, "today": 26, "marks": [29]}  # Oct 1 2026 = Thu
    assert card.month(date(2028, 2, 10), [])["days"] == 29  # leap year
    assert card.plain({"m": "I’ve — ok…", "d": [["In 3 days", "Café"]], "n": 5}) ==         {"m": "I've - ok...", "d": [["In 3 days", "Caf"]], "n": 5}  # card fonts are ASCII only


if __name__ == "__main__":
    for t in [test_countdown, test_steps_ok, test_cold_start, test_predictor, test_rain, test_month]:
        t()
    print(f"steps/rain/calendar: 6/6 pass (predictor backend: {predictor.BACKEND})")
