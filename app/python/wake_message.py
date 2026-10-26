"""Wake message (spec F3): short wording from the local model, every number checked."""
import requests

import config as C
from validator import validate


def facts(rec):
    n = rec["night"]
    lines = [f"Alarm: {rec['final_alarm']} (usual {rec['normal_alarm']}, extra {rec['extra_min']} min)."]
    if n.get("confident"):
        lines.append(f"Night score: {n['score']} out of 100.")
    else:
        lines.append("Night score: not sure (not enough radar data).")
    if rec.get("rain") and rec["rain"].get("detected") and rec["rain"].get("confident"):
        lines.append("It is raining.")
    return " ".join(lines)


def template(rec):
    n = rec["night"]
    if not n.get("confident"):
        return f"Good morning. Not sure how you slept, so the alarm stayed at {rec['final_alarm']}."
    if rec["extra_min"]:
        return (f"Good morning. Night score {n['score']}, so you got {rec['extra_min']} extra minutes. "
                f"Up at {rec['final_alarm']}.")
    return f"Good morning. Night score {n['score']}. Up at {rec['final_alarm']}."


def _ask(system, user):
    r = requests.post(f"{C.LLM_URL}/v1/chat/completions", timeout=C.LLM_TIMEOUT_S, json={
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": 60, "temperature": 0.3})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip().strip('"')


def wake_message(rec):
    """Returns (text, source, problems). source: 'model', 'model-retry' or 'template'."""
    f = facts(rec)
    tries = [
        ("model", "You are a kind, calm bedside clock. Write one or two short sentences to wake the user. "
                  "Use only the facts given. No snooze.", f),
        ("model-retry", "Write one short wake-up sentence. Copy numbers exactly; use no other numbers or times. "
                        f"Allowed: {rec['final_alarm']}, {rec['extra_min']}"
                        + (f", {rec['night']['score']}" if rec["night"].get("confident") else "") + ".", f),
    ]
    problems = []
    for source, system, user in tries:
        try:
            text = _ask(system, user)
        except Exception as e:  # server down or slow: fall back, the alarm still rings
            problems.append(f"{source}: {type(e).__name__}")
            break
        ok, why = validate(text, rec)
        if ok:
            return text, source, problems
        problems.append(f"{source}: {'; '.join(why)} | {text}")
    return template(rec), "template", problems
