"""Night score checks on synthetic rows. Run: python tests/test_nightscore.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "python"))
from nightscore import night_score  # noqa: E402


def rows(n, move=0, presence=100, breath=14.0, t0=0):
    return [{"ts": t0 + i * 10, "presence": presence, "breath": breath, "move_max": move} for i in range(n)]


def test_cases():
    calm = night_score(rows(360), 0, 3600, 5)
    assert calm["score"] == 100 and calm["confident"], calm
    restless = night_score(rows(360, move=60), 0, 3600, 5)
    assert restless["restless_min"] == 60 and restless["long_awakenings"] == 1 and restless["score"] == 0, restless
    half = night_score(rows(180) + rows(180, move=60, t0=1800), 0, 3600, 5)
    assert half["restless_min"] == 30 and 30 <= half["score"] <= 50, half
    jumpy = [{"ts": i * 10, "presence": 100, "breath": 10.0 if i % 2 else 20.0, "move_max": 0} for i in range(360)]
    assert night_score(jumpy, 0, 3600, 5)["irregular_min"] >= 58
    assert not night_score(rows(360, presence=0), 0, 3600, 5)["confident"]
    assert not night_score(rows(100), 0, 3600, 5)["confident"]
    assert not night_score(rows(30), 0, 300, 60)["confident"]  # real nights need 60 min


if __name__ == "__main__":
    test_cases()
    print("night score: all pass")
