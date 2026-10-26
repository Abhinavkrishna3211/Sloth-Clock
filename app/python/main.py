"""Sloth Clock - Linux side: logging, night score, alarm decision, wake, tiny steps, rain, card, web page."""
import re
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta

from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.web_ui import WebUI

import card
import config as C
import rain
import tasks
from decision import decide
from nightscore import night_score
from store import Store
from wake_message import wake_message

log = Logger("sloth")
real = Store(C.REAL_DB)
demo_db = Store(C.DEMO_DB)
live = deque(maxlen=30)  # last 5 min of 10 s rows, for the page only
demo = {"active": False, "t0": 0, "minutes": 0}
wake = {"state": 0, "day": None}  # 0 idle, 1 sunrise, 2 ringing, 6 backup alarm ringing
WAKE_NAMES = {1: "sunrise", 2: "ringing", 3: "dismissed", 4: "timed_out", 5: "stopped", 6: "backup_alarm"}
HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
timers = {"arm": 0, "mic": None, "night_card": None}
card_state = {"date_offset": 0, "last": None}


def store():
    return demo_db if demo["active"] else real


# ---------- from the MCU ----------
def on_row(lines, bad, presence, breath_x10, heart_x10, dist, move_max, move_mean_x10):
    r = {"ts": time.time(), "lines": lines, "bad": bad, "presence": presence,
         "breath": breath_x10 / 10, "heart": heart_x10 / 10, "distance": dist,
         "move_max": move_max, "move_mean": move_mean_x10 / 10}
    live.append(r)
    store().add_row(r, r["ts"])


def on_mic(blocks, rms, b1, b2, b3, b4, flat, imp):
    store().add_mic({"ts": time.time(), "blocks": blocks, "rms": rms, "b1": b1, "b2": b2, "b3": b3,
                     "b4": b4, "flat": flat, "imp": imp})


def on_wake_state(n):
    wake["state"] = n if n in (1, 2, 6) else 0
    store().event("wake", f"{WAKE_NAMES.get(n, n)} {wake['day']}")


def on_button(kind):
    store().event("button", "long" if kind else "short")
    if kind:
        step_done()


Bridge.provide("radar_row", on_row)
Bridge.provide("mic_row", on_mic)
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


def rain_now(db):
    if real.get_settings(C.DEFAULT_SETTINGS)["rain"] != "1":
        return None
    return rain.detect(db.mic_since(time.time() - 3600), real.rain_labels())


def make_decision(db, key, normal, hard, rows, start, end, min_minutes):
    night = night_score(rows, start, end, min_minutes)
    rec = decide(normal, hard, night, rain_now(db), shifted_on(normal.date() - timedelta(days=1)))
    db.save_decision(key, rec)
    db.event("decision", f"{key} {rec['final_alarm']} +{rec['extra_min']}")
    log.info(f"decision {key}: {rec}")

    def write():  # the models are slow; the alarm never waits for them
        try:
            plan_step(db, key, normal, rec)
        except Exception as e:
            log.error(f"plan_step failed: {e}")
        text, source, problems = wake_message(rec)
        db.set_message(key, text)
        db.event("message", f"{key} {source} {problems}")
        log.info(f"message ({source}): {text} {problems}")
        push_card("morning")
    threading.Thread(target=write, daemon=True).start()
    return rec


def start_wake(day_key, sunrise_s):
    wake["day"] = day_key
    try:
        Bridge.call("wake_start", int(sunrise_s), timeout=5)
        Bridge.call("backup_arm", -1, timeout=5)
    except Exception as e:
        log.error(f"wake_start failed: {e}")


# ---------- one tiny step a day ----------
def plan_step(db, key, normal, rec):
    today = normal.date()
    job = tasks.pick_job(real.items(), today)
    if not job:
        return
    n = rec["night"]
    score = n["score"] if n.get("confident") else None
    hist = db.history(key)
    recent = [d for _, d in hist[-7:]]
    rate = sum(recent) / len(recent) if recent else 0.5

    def feats(size):
        return tasks.features(score, today, job, size, rate, normal.hour, rec["extra_min"])
    size, info = tasks.choose_size(hist, feats)
    db.save_morning(key, job["id"], size, job["steps"][size], feats(size), info)
    db.event("step", f"{key} {size} {info}")


def newest_db():
    r, d = real.last_decision(), demo_db.last_decision()
    return demo_db if d and (not r or d["ts"] > r["ts"]) else real


def today_step():
    db = newest_db()
    d = db.last_decision()
    m = d and db.morning(d["day"])
    if not m:
        return None
    return {**m, "minutes": tasks.SIZE_MIN[m["size"]], "demo": db is demo_db}


def step_done():
    m = today_step()
    if not m:
        return False
    db = demo_db if m["demo"] else real
    db.set_morning_done(m["day"])
    db.event("step_done", m["day"])
    return True


# ---------- e-paper card ----------
def push_card(view=None):
    now = datetime.now(C.TZ)
    s = real.get_settings(C.DEFAULT_SETTINGS)
    if view is None:
        view = "night" if now.strftime("%H:%M") >= C.BEDTIME else "morning"
    dates = tasks.upcoming(real.items(), now.date(), k=10)
    off = card_state["date_offset"] % len(dates) if dates else 0
    d = newest_db().last_decision()
    m = today_step()
    step = f"{m['step']} ({m['minutes']} min)" if m and not m["done"] else ""
    c = card.content(view, now, s, d, (dates[off:] + dates[:off])[:3], step, d and d["message"],
                     [date.fromisoformat(x["due"]) for x in dates])
    ok, detail = card.push(s["card_url"], c)
    card_state["last"] = {"ts": time.time(), "ok": ok, "detail": detail}
    real.event("card", f"{view} {ok} {detail}")
    return ok, detail


# ---------- main loop ----------
def housekeeping(now, s):
    """Backup alarm arming, microphone on/off, bedtime card. Never blocks the alarm."""
    if timers["mic"] != s["rain"]:
        try:
            Bridge.call("mic_enable", s["rain"] == "1", timeout=5)
            timers["mic"] = s["rain"]
        except Exception as e:
            log.error(f"mic_enable failed: {e}")
    if time.time() - timers["arm"] >= 60:  # re-armed every minute; if Linux stops, the MCU still rings
        timers["arm"] = time.time()
        secs = -1
        if s["enabled"] == "1":
            normal, _ = next_alarm(now, s)
            key = normal.strftime("%Y-%m-%d")
            d = real.decision(key)
            target = at(normal.date(), d["record"]["final_alarm"]) if d else normal
            left = (target - now).total_seconds() + C.BACKUP_GRACE_S
            if wake["day"] != key and 0 < left < 86400:
                secs = int(left)
        try:
            Bridge.call("backup_arm", secs, timeout=5)
        except Exception as e:
            log.error(f"backup_arm failed: {e}")
    day = now.strftime("%Y-%m-%d")
    if now.strftime("%H:%M") >= C.BEDTIME and timers["night_card"] != day:
        timers["night_card"] = day
        threading.Thread(target=push_card, args=("night",), daemon=True).start()


def tick():
    now = datetime.now(C.TZ)
    s = real.get_settings(C.DEFAULT_SETTINGS)
    housekeeping(now, s)

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
    now = datetime.now(C.TZ)
    normal, hard = next_alarm(now, s)
    today = now.date()
    return {
        "rows": list(live),
        "night": night_score(rows, start, time.time(), mins) if rows else None,
        "settings": s,
        "next_alarm": normal.strftime("%a %H:%M"),
        "demo": {**demo, "left_s": max(0, int(demo["t0"] + demo["minutes"] * 60 - time.time()))
                 if demo["active"] else 0},
        "wake": WAKE_NAMES.get(wake["state"], "idle"),
        "decision": newest_db().last_decision(),
        "items": [{**i, "when": tasks.countdown(date.fromisoformat(i["due"]), today) if i["due"] else ""}
                  for i in real.items()],
        "step": today_step(),
        "rain": rain_now(store()),
        "rain_labels": len(real.rain_labels()),
        "predictor": tasks.predictor.BACKEND,
        "card": card_state["last"],
    }


def api_settings(body: dict):
    keys = ("normal_alarm", "hard_limit", "enabled", "rain", "card_url")
    s = {k: str(body[k]).strip() for k in keys if k in body}
    for k in ("normal_alarm", "hard_limit"):
        if k in s and not HHMM.fullmatch(s[k]):
            return {"ok": False, "error": f"{k} must be HH:MM"}
    for k in ("enabled", "rain"):
        if s.get(k, "1") not in ("0", "1"):
            return {"ok": False, "error": f"{k} must be 0 or 1"}
    if s.get("card_url") and not re.fullmatch(r"http://[\w.\-:]{1,80}", s["card_url"]):
        return {"ok": False, "error": "card address must look like http://192.168.1.50"}
    for k, v in s.items():
        real.set_setting(k, v)
    real.event("settings", str(s))
    timers["arm"] = 0  # re-arm the backup alarm with the new times
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


def _call(name, *args):
    try:
        Bridge.call(name, *args, timeout=5)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def api_dismiss():
    return _call("wake_stop")


def api_chime():
    return _call("chime_test")


def api_inject(body: dict):  # one radar CSV line (tests) into the MCU parser
    return _call("inject_line", str(body.get("line", ""))[:90])


def api_item_add(body: dict):
    title = str(body.get("title", "")).strip()[:100]
    kind = body.get("kind", "date")
    due = str(body.get("due") or "").strip() or None
    if not title or kind not in ("date", "job"):
        return {"ok": False, "error": "title and kind (date or job) needed"}
    if due:
        try:
            date.fromisoformat(due)
        except ValueError:
            return {"ok": False, "error": "date must be YYYY-MM-DD"}
    elif kind == "date":
        return {"ok": False, "error": "an important date needs a date"}
    item_id = real.add_item(title, due, kind)
    if kind == "job":
        def split():
            steps, source = tasks.split_job(title)
            real.set_steps(item_id, steps)
            real.event("steps", f"{item_id} {source}")
        threading.Thread(target=split, daemon=True).start()
    real.event("item", f"add {item_id} {kind}")
    return {"ok": True, "id": item_id}


def api_item_delete(body: dict):
    real.delete_item(int(body.get("id", 0)))
    return {"ok": True}


def api_item_done(body: dict):
    real.set_item_done(int(body.get("id", 0)), 1)
    return {"ok": True}


def api_item_steps(body: dict):
    steps = {k: str(body.get(k, "")).strip()[:120] for k in tasks.SIZES}
    if not all(steps.values()):
        return {"ok": False, "error": "all three sizes needed"}
    real.set_steps(int(body.get("id", 0)), steps)
    return {"ok": True}


def api_step_done():
    return {"ok": step_done()}


def api_rain_label(body: dict):
    """Labels the last 3 minutes of mic data as rain / not rain (training rows for the classifier)."""
    mins = rain.minutes(real.mic_since(time.time() - 180))
    for m in mins:
        real.add_rain_label(m["x"], bool(body.get("rain")))
    return {"ok": bool(mins), "labelled": len(mins), "error": None if mins else "no mic data in the last 3 min"}


def api_card_key(body: dict):
    """E-paper card buttons: KEY0 short = dismiss, KEY0 long = step done, KEY1 = next date, KEY2 = refresh."""
    key = body.get("key")
    real.event("card_key", str(key))
    if key == "dismiss":
        return api_dismiss()
    if key == "done":
        ok = step_done()
        threading.Thread(target=push_card, daemon=True).start()
        return {"ok": ok}
    if key in ("next", "refresh"):
        card_state["date_offset"] += key == "next"
        threading.Thread(target=push_card, daemon=True).start()
        return {"ok": True}
    return {"ok": False, "error": "unknown key"}


def api_card_push():
    ok, detail = push_card()
    return {"ok": ok, "error": None if ok else detail}


ui.expose_api("GET", "/api/live", api_live)
ui.expose_api("POST", "/api/settings", api_settings)
ui.expose_api("POST", "/api/demo/start", api_demo_start)
ui.expose_api("POST", "/api/demo/stop", api_demo_stop)
ui.expose_api("POST", "/api/dismiss", api_dismiss)
ui.expose_api("POST", "/api/chime", api_chime)
ui.expose_api("POST", "/api/inject", api_inject)
ui.expose_api("POST", "/api/radar", api_inject)
ui.expose_api("POST", "/api/items", api_item_add)
ui.expose_api("POST", "/api/items/delete", api_item_delete)
ui.expose_api("POST", "/api/items/done", api_item_done)
ui.expose_api("POST", "/api/items/steps", api_item_steps)
ui.expose_api("POST", "/api/step/done", api_step_done)
ui.expose_api("POST", "/api/rain/label", api_rain_label)
ui.expose_api("POST", "/api/card/key", api_card_key)
ui.expose_api("POST", "/api/card/push", api_card_push)

App.run(user_loop=tick)
