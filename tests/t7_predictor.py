"""T7: step-size predictor on synthetic mornings (no real history yet), held-out accuracy and timing.
Runs inside the app container with the venv python so TabPFN is used:
docker exec -e PYTHONPATH=/app/python sloth-clock-main-1 /app/.cache/.venv/bin/python /app/tests/t7_predictor.py"""
import random
import sys
import time

sys.path.insert(0, "/app/python")
import predictor  # noqa: E402
import tasks  # noqa: E402

# Synthetic rule with 10% label noise: a step gets done when the night was good enough for its size.
rnd = random.Random(7)
rows = []
for _ in range(120):
    score, size, day = rnd.randint(15, 95), rnd.randint(0, 2), rnd.randint(0, 6)
    done = score - 20 * size + (10 if day >= 5 else 0) > 50
    if rnd.random() < 0.1:
        done = not done
    rows.append(([score, day, rnd.randint(-1, 20), size, rnd.random(), rnd.choice([6, 7, 8]), rnd.choice([0, 15, 30])],
                 int(done)))
train, test = rows[:80], rows[80:]

cold = [(s, n) for s in (40, 69, 70) for n in (0, 19)]
for score, n in cold:
    size, info = tasks.choose_size([([0] * 7, 1)] * n, lambda s: [score, 0, -1, tasks.SIZES.index(s), 0, 6, 0])
    print(f"cold start score={score} rows={n}: {size} {info}")

backends = ["logistic"] + (["tabpfn"] if predictor.BACKEND == "tabpfn" else [])
for b in backends:
    t = time.time()
    m = predictor.fit([r[0] for r in train], [r[1] for r in train], quick=(b == "logistic"))
    t_fit = time.time() - t
    t = time.time()
    p = predictor.p_true(m, [r[0] for r in test])
    t_pred = time.time() - t
    acc = sum((pi >= 0.5) == bool(r[1]) for pi, r in zip(p, test)) / len(test)
    print(f"{b}: held-out accuracy {acc:.2f} on {len(test)} rows, fit {t_fit:.1f} s, predict {t_pred:.1f} s")
