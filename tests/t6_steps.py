"""T6: step splitting by the local model for 5 example jobs. Runs inside the app container:
docker exec sloth-clock-main-1 python /app/tests/t6_steps.py"""
import sys
import time

sys.path.insert(0, "/app/python")
from tasks import split_job  # noqa: E402

# Example jobs for the test, not anyone's real list
jobs = ["File the 2026 tax return", "Clean the garage", "Reply to the landlord's email",
        "Back up the laptop photos", "Book a dentist appointment"]
counts = {"model": 0, "template": 0}
for title in jobs:
    t = time.time()
    steps, source = split_job(title)
    counts[source] += 1
    print(f"{time.time() - t:5.1f}s {source:8} {title!r}")
    for size, text in steps.items():
        print(f"         {size:6} {text}")
print(counts)
