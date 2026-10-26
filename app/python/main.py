"""Sloth Clock - Linux side: logging, night score, alarm decision, wake, web page."""
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta

from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.web_ui import WebUI

import config as C
from decision import decide
from nightscore import night_score
from store import Store
from wake_message import wake_message

log = Logger("sloth")
real = Store(C.REAL_DB)
demo_db = Store(C.DEMO_DB)
live = deque(maxlen=30)  # last 5 min of 10 s rows, for the page only
demo = {"active": False, "t0": 0, "minutes": 0}
wake = {"state": 0, "day": None}  # 0 idle, 1 sunrise, 2 ringing
WAKE_NAMES = {1: "sunrise", 2: "ringing", 3: "dismissed", 4: "timed_out", 5: "stopped"}
HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def store():
    return demo_db if demo["active"] else real


# ---------- from the MCU ----------
def on_row(lines, bad, presence, breath_x10, heart_x10, dist, move_max, move_mean_x10):
    r = {"ts": time.time(), "lines": lines, "bad": bad, "presence": presence,
         "breath": breath_x10 / 10, "heart": heart_x10 / 10, "distance": dist,
         "move_max": move_max, "move_mean": move_mean_x10 / 10}
    live.append(r)
    store().add_row(r, r["ts"])


def on_wake_state(n):
    wake["state"] = n if n in (1, 2) else 0
    store().event("wake", f"{WAKE_NAMES.get(n, n)} {wake['day']}")


def on_button(kind):
    store().event("button", "long" if kind else "short")


Bridge.provide("radar_row", on_row)
Bridge.provide("wake_state", on_wake_state)
Bridge.provide("button", on_button)


# ---------- alarm ----------
def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=C.TZ)


def next_alarm(now, s):
    """The alarm we are heading for: today's, until 40 min after it, then tomorrow's."""
    day = now.date()
    if now > at(day, s["normal_alarm"]) + timedelta(minutes=40):
        day += timedelta(days=1)
    return at(day, s["normal_alarm"]), at(day, s["hard_limit"])


def shifted_on(day):
    d = real.decision(day.strftime("%Y-%m-%d"))
    return bool(d and d["record"]["extra_min"] > 0)


def make_decision(db, key, normal, hard, rows, start, end, min_minutes):
    night = night_score(rows, start, end, min_minutes)
    rec = decide(normal, hard, night, None, shifted_on(normal.date() - timedelta(days=1)))
    db.save_decision(key, rec)
    db.event("decision", f"{key} {rec['final_alarm']} +{rec['extra_min']}")
    log.info(f"decision {key}: {rec}")

    def write():  # the model is slow; the alarm never waits for it
        text, source, problems = wake_message(rec)
        db.set_message(key, text)
        db.event("message", f"{key} {source} {problems}")
        log.info(f"message ({source}): {text} {problems}")
    threading.Thread(target=write, daemon=True).start()
    return rec


def start_wake(day_key, sunrise_s):
    wake["day"] = day_key
    try:
        Bridge.call("wake_start", int(sunrise_s), timeout=5)
    except Exception as e:
        log.error(f"wake_start failed: {e}")


def tick():
    now = datetime.now(C.TZ)
    s = real.get_settings(C.DEFAULT_SETTINGS)

    if demo["active"]:
        if time.time() >= demo["t0"] + demo["minutes"] * 60:
            normal, hard = next_alarm(now, s)
            key = "demo-" + now.strftime("%Y%m%d-%H%M%S")
            rows = demo_db.rows_since(demo["t0"])
            rec = make_decision(demo_db, key, normal, hard, rows, demo["t0"], time.time(), C.MIN_MINUTES_DEMO)
            demo_db.event("demo", f"wake now; the real alarm would be {rec['final_alarm']}")
            demo["active"] = False
            start_wake(key, C.DEMO_SUNRISE_S)
    elif s["enabled"] == "1":
        normal, hard = next_alarm(now, s)
        key = normal.strftime("%Y-%m-%d")
        d = real.decision(key)
        if d is None and normal - timedelta(minutes=C.DECISION_LEAD_MIN) <= now < normal:
            start = (normal - timedelta(hours=C.NIGHT_HOURS)).timestamp()
            make_decision(real, key, normal, hard, real.rows_since(start), start, now.timestamp(),
                          C.MIN_MINUTES_REAL)
            d = real.decision(key)
        if d and wake["day"] != key:
            final = at(normal.date(), d["record"]["final_alarm"])
            left = (final - now).total_seconds()
            if -60 < left <= C.SUNRISE_S:  # sunrise ends exactly at the final alarm time
                start_wake(key, max(0, left))
    time.sleep(2)


# ---------- web page ----------
ui = WebUI()


def api_live():
    if demo["active"]:
        rows, start, mins = demo_db.rows_since(demo["t0"]), demo["t0"], C.MIN_MINUTES_DEMO
    else:
        start = time.time() - C.NIGHT_HOURS * 3600
        rows, mins = real.rows_since(start), C.MIN_MINUTES_REAL
    s = real.get_settings(C.DEFAULT_SETTINGS)
    normal, hard = next_alarm(datetime.now(C.TZ), s)
    last = max(filter(None, (real.last_decision(), demo_db.last_decision())),
               key=lambda d: d["ts"], default=None)
    return {
        "rows": list(live),
        "night": night_score(rows, start, time.time(), mins) if rows else None,
        "settings": s,
        "next_alarm": normal.strftime("%a %H:%M"),
        "demo": {**demo, "left_s": max(0, int(demo["t0"] + demo["minutes"] * 60 - time.time()))
                 if demo["active"] else 0},
        "wake": WAKE_NAMES.get(wake["state"], "idle"),
        "decision": last,
    }


def api_settings(body: dict):
    s = {k: str(body[k]) for k in ("normal_alarm", "hard_limit", "enabled") if k in body}
    for k in ("normal_alarm", "hard_limit"):
        if k in s and not HHMM.fullmatch(s[k]):
            return {"ok": False, "error": f"{k} must be HH:MM"}
    if s.get("enabled", "1") not in ("0", "1"):
        return {"ok": False, "error": "enabled must be 0 or 1"}
    for k, v in s.items():
        real.set_setting(k, v)
    real.event("settings", str(s))
    return {"ok": True}


def api_demo_start(body: dict):
    minutes = int(body.get("minutes", C.DEMO_DEFAULT_MIN))
    if not 1 <= minutes <= 60:
        return {"ok": False, "error": "minutes must be 1-60"}
    demo.update(active=True, t0=time.time(), minutes=minutes)
    demo_db.event("demo", f"start {minutes} min")
    return {"ok": True}


def api_demo_stop():
    demo["active"] = False
    demo_db.event("demo", "stopped")
    return {"ok": True}


def api_dismiss():
    try:
        Bridge.call("wake_stop", timeout=5)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def api_chime():
    try:
        Bridge.call("chime_test", timeout=5)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def api_inject(body: dict):  # test hook: feed one radar CSV line to the MCU parser
    line = str(body.get("line", ""))[:90]
    try:
        Bridge.call("inject_line", line, timeout=5)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


ui.expose_api("GET", "/api/live", api_live)
ui.expose_api("POST", "/api/settings", api_settings)
ui.expose_api("POST", "/api/demo/start", api_demo_start)
ui.expose_api("POST", "/api/demo/stop", api_demo_stop)
ui.expose_api("POST", "/api/dismiss", api_dismiss)
ui.expose_api("POST", "/api/chime", api_chime)
ui.expose_api("POST", "/api/inject", api_inject)

App.run(user_loop=tick)
