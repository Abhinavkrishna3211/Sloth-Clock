"""E-paper card (spec F4): builds the card content and posts it to the EE04 on local Wi-Fi."""
import calendar

import requests

# The card's fonts only have plain ASCII: turn the model's curly quotes and dashes into it.
PLAIN = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                       "–": "-", "—": "-", "…": "..."})


def plain(v):
    if isinstance(v, str):
        return v.translate(PLAIN).encode("ascii", "ignore").decode()
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [plain(x) for x in v]
    return v


def month(today, marked):
    """Mini calendar: first weekday of the month (Mon=0), number of days, today, and days with a date set."""
    first, days = calendar.monthrange(today.year, today.month)
    return {"title": today.strftime("%B %Y"), "first": first, "days": days, "today": today.day,
            "marks": sorted({d.day for d in marked if (d.year, d.month) == (today.year, today.month)})}


def content(view, today, settings, decision, dates, step, message=None, marked=()):
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
        "cal": month(today, marked),
        "step": step or "",
        "message": (message or "")[:200] if view == "morning" else "Watching your sleep.",
    }


def push(url, card, timeout=8):
    """Returns (ok, detail). Never raises: the alarm must not depend on the card."""
    if not url:
        return False, "no card address set"
    try:
        r = requests.post(url.rstrip("/") + "/show", json=plain(card), timeout=timeout)
        return r.ok, f"HTTP {r.status_code}"
    except Exception as e:
        return False, type(e).__name__
