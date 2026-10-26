"""Wake message (spec F3): short wording from the local model, every number checked."""
import re

import requests

import config as C
from validator import validate


def reason(rec):
    """Plain-words reason for the alarm time, built by code so the model only rephrases it."""
    n, rain = rec["night"], rec.get("rain") or {}
    rainy = rain.get("detected") and rain.get("confident")
    if not n.get("confident"):
        return "I am not sure how you slept, so I kept your usual alarm."
    if rec["extra_min"] == 0:
        if rec["shifted_yesterday"] and (n["score"] < 60 or rainy):
            return "You slept badly, but you already slept in yesterday, so no extra time today."
        if rec["slack_min"] == 0 and (n["score"] < 60 or rainy):
            return "You slept badly, but there was no time to spare before you must be up."
        return "You slept well, so the alarm stayed at the usual time."
    why = []
    if n["score"] < 60:
        why.append("you slept badly")
    if rainy:
        why.append("it is raining")
    return f"Because {' and '.join(why)}, I let you sleep {rec['extra_min']} minutes longer."


def facts(rec):
    f = f"Wake time: {rec['final_alarm']}. {reason(rec)}"
    if rec["night"].get("confident"):
        f += f" Night score: {rec['night']['score']} out of 100."
    return f


def template(rec):
    return f"Good morning. It is {rec['final_alarm']}. {reason(rec)}"


def _ask(system, user):
    r = requests.post(f"{C.LLM_URL}/v1/chat/completions", timeout=C.LLM_TIMEOUT_S, json={
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": 60, "temperature": 0})
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return re.sub(r"\s+", " ", text).strip().strip('"')


def wake_message(rec):
    """Returns (text, source, problems). source: 'model', 'model-retry' or 'template'."""
    f = facts(rec)
    example = ("Example. Facts: Wake time: 07:10. Because you slept badly, I let you sleep 15 minutes longer. "
               "Answer: Morning, sleepyhead. You had a rough night, so I let you stay in bed a little longer.\n"
               "Now. Facts: " + f + " Answer:")
    tries = [
        ("model", "You are a sleepy, kind sloth who lives in a bedside clock. Wake the user in one or two short "
                  "sentences. Say the reason kindly. Use only the facts given, add nothing else.", example),
        ("model-retry", "Rewrite the reason as one friendly wake-up sentence. Use no numbers or times.", reason(rec)),
    ]
    problems = []
    for source, system, user in tries:
        try:
            text = _ask(system, user)
        except Exception as e:  # server down or slow: fall back, the alarm still rings
            problems.append(f"{source}: {type(e).__name__}")
            break
        ok, why = validate(text, rec)
        if ok:  # the time always comes from code, never from the model
            if not validate(text, rec, need_time=True)[0]:
                text = f"{rec['final_alarm']}. {text}"
            return text, source, problems
        problems.append(f"{source}: {'; '.join(why)} | {text}")
    return template(rec), "template", problems
