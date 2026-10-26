"""E-paper card (spec F4): builds the card content and posts it to the EE04 on local Wi-Fi."""
import requests


def content(view, today, settings, decision, dates, step, message=None):
    """view: 'night' or 'morning'. Everything here is computed by code; the card only draws it."""
    alarm = settings["normal_alarm"]
    if decision:
        r = decision["record"]
        alarm = r["final_alarm"] + (f" (+{r['extra_min']})" if r["extra_min"] else "")
    return {
        "view": view,
        "date": today.strftime("%a %d %b"),
        "alarm": alarm if settings.get("enabled", "1") == "1" else "off",
        "limit": settings["hard_limit"],
        "dates": [[d["when"], d["title"][:40]] for d in dates[:3]],
        "step": step or "",
        "message": (message or "")[:200] if view == "morning" else "Watching your sleep.",
    }


def push(url, card, timeout=8):
    """Returns (ok, detail). Never raises: the alarm must not depend on the card."""
    if not url:
        return False, "no card address set"
    try:
        r = requests.post(url.rstrip("/") + "/show", json=card, timeout=timeout)
        return r.ok, f"HTTP {r.status_code}"
    except Exception as e:
        return False, type(e).__name__
