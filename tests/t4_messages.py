"""T4: wake messages from the local model for 10 decision records. Runs inside the app container:
docker exec sloth-clock-main-1 python /app/tests/t4_messages.py"""
import sys
import time
from datetime import datetime

sys.path.insert(0, "/app/python")
from decision import decide  # noqa: E402
from wake_message import wake_message  # noqa: E402

N = datetime(2026, 10, 27, 6, 30)
RAIN = {"detected": True, "confident": True}
cases = [(85, True, None, False, 30), (55, True, None, False, 30), (55, True, RAIN, False, 30),
         (55, True, RAIN, False, 10), (55, True, None, True, 30), (35, True, None, True, 30),
         (20, False, None, False, 30), (72, True, RAIN, False, 30), (45, True, None, False, 0),
         (10, True, RAIN, False, 60)]
counts = {"model": 0, "model-retry": 0, "template": 0}
for score, conf, rain, shifted, slack in cases:
    hard = N.replace(hour=6 + (30 + slack) // 60, minute=(30 + slack) % 60)
    rec = decide(N, hard, {"score": score, "confident": conf, "out_of": 100}, rain, shifted)
    t = time.time()
    text, source, problems = wake_message(rec)
    counts[source] += 1
    print(f"{time.time() - t:5.1f}s {source:11} +{rec['extra_min']:<2} {text!r} {problems}")
print(counts)
