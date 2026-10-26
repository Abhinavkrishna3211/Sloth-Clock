"""Important dates and postponed jobs (spec F5, F6): countdowns, step splitting, one tiny step a day."""
import json
import re
from datetime import date

import requests

import config as C
import predictor

SIZES = ["tiny", "small", "normal"]
SIZE_MIN = {"tiny": 5, "small": 15, "normal": 30}
COLD_START_ROWS = 20
P_DONE_MIN = 0.6
NUM_RE = re.compile(r"\d+")


def countdown(due: date, today: date) -> str:
    n = (due - today).days
    return "Today" if n == 0 else "Tomorrow" if n == 1 else f"In {n} days" if n > 1 else f"{-n} days ago"


def upcoming(items, today, k=3):
    dated = [i for i in items if i["due"] and not i["done"] and date.fromisoformat(i["due"]) >= today]
    dated.sort(key=lambda i: i["due"])
    return [{"title": i["title"], "due": i["due"], "when": countdown(date.fromisoformat(i["due"]), today)}
            for i in dated[:k]]


# ---------- step splitting ----------
def steps_ok(steps, title):
    """Steps may use only numbers from the job title, plus the step durations 5/15/30."""
    allowed = set(NUM_RE.findall(title)) | {"5", "15", "30"}
    if set(steps) != set(SIZES):
        return False, ["missing sizes"]
    bad = [n for s in SIZES for n in NUM_RE.findall(steps[s]) if n not in allowed]
    too_long = [s for s in SIZES if not steps[s].strip() or len(steps[s]) > 120]
    problems = [f"number {n} not in the job" for n in bad] + [f"{s} step empty or too long" for s in too_long]
    return not problems, problems


def fallback_steps(title):
    return {"tiny": f"Open what you need for: {title}. Just look at it.",
            "small": f"Do the first easy part of: {title}.",
            "normal": f"Work on {title} until a timer rings."}


def split_job(title):
    """Asks the local model for one first step at three sizes. Returns (steps, source)."""
    prompt = (f"Job: {title}\nWrite the very first step of this job at three sizes. "
              "Reply only with JSON like {\"tiny\": \"...\", \"small\": \"...\", \"normal\": \"...\"}. "
              "tiny takes 5 minutes, small 15 minutes, normal 30 minutes. Short plain sentences. "
              "Do not add dates or numbers.")
    try:
        r = requests.post(f"{C.LLM_URL}/v1/chat/completions", timeout=C.LLM_TIMEOUT_S, json={
            "messages": [{"role": "user", "content": prompt}], "max_tokens": 120, "temperature": 0})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        steps = json.loads(text[text.index("{"):text.rindex("}") + 1])
        steps = {k: str(steps.get(k, "")).strip() for k in SIZES}
        ok, _ = steps_ok(steps, title)
        if ok:
            return steps, "model"
    except Exception:
        pass
    return fallback_steps(title), "template"


# ---------- which job, which size ----------
def pick_job(items, today):
    jobs = [i for i in items if i["kind"] == "job" and not i["done"] and i["steps"]]
    if not jobs:
        return None
    return min(jobs, key=lambda i: (i["due"] or "9999-12-31", i["created"]))


def features(night_score, today, job, size, past_rate, wake_hour, extra_min):
    due = (date.fromisoformat(job["due"]) - today).days if job and job["due"] else -1
    return [night_score if night_score is not None else -1, today.weekday(), due,
            SIZES.index(size), past_rate, wake_hour, extra_min]


def choose_size(history, feats_for):
    """history: list of (features, done). feats_for(size) -> features.

    Under 20 labelled mornings: score >= 70 -> small, else tiny, never normal.
    After that: the largest size with P(done) >= 0.6, else tiny.
    Returns (size, info) where info explains the choice.
    """
    score = feats_for("tiny")[0]
    if len(history) < COLD_START_ROWS:
        size = "small" if score >= 70 else "tiny"
        return size, {"method": "rule", "rows": len(history), "score": score}
    model = predictor.fit([h[0] for h in history], [int(h[1]) for h in history])
    if model is None:
        return "tiny", {"method": "rule", "rows": len(history), "note": "only one outcome so far"}
    probs = dict(zip(SIZES, predictor.p_true(model, [feats_for(s) for s in SIZES])))
    size = next((s for s in reversed(SIZES) if probs[s] >= P_DONE_MIN), "tiny")
    return size, {"method": predictor.BACKEND, "rows": len(history),
                  "p_done": {k: round(v, 2) for k, v in probs.items()}}
