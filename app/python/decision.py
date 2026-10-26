"""Alarm decision (spec F2). Health limits are fixed here on purpose: not in config, not on the web page."""
from datetime import datetime, timedelta

MAX_EXTRA_MIN = 30      # never more than 30 extra minutes
RESTLESS_SCORE = 60     # night score below this -> +15
VERY_POOR_SCORE = 40    # below this a shift is allowed even after yesterday's shift
RESTLESS_BONUS = 15
RAIN_BONUS = 15


def decide(normal_alarm: datetime, hard_limit: datetime, night: dict,
           rain: dict | None, shifted_yesterday: bool) -> dict:
    """night: {"score", "confident", ...}; rain: {"detected", "confident"} or None.

    Returns the full decision record: inputs, rules that fired, final time.
    There is no snooze: the result is one alarm time, never later than hard_limit.
    """
    slack = max(0, int((hard_limit - normal_alarm).total_seconds() // 60))
    rules, extra = [], 0

    night_ok = bool(night.get("confident"))
    score = night.get("score")
    if not night_ok:
        rules.append("night score not confident: contributes 0")
    elif score < RESTLESS_SCORE:
        extra += RESTLESS_BONUS
        rules.append(f"restless night (score {score} < {RESTLESS_SCORE}): +{RESTLESS_BONUS}")
    very_poor = night_ok and score < VERY_POOR_SCORE

    if rain is not None:
        if not rain.get("confident"):
            rules.append("rain not confident: contributes 0")
        elif rain.get("detected"):
            extra += RAIN_BONUS
            rules.append(f"rain in the last 60 min: +{RAIN_BONUS}")

    wanted = extra
    extra = min(MAX_EXTRA_MIN, slack, extra)
    if extra < wanted:
        rules.append(f"capped to {extra} (max {MAX_EXTRA_MIN}, slack {slack})")
    if extra and shifted_yesterday and not very_poor:
        extra = 0
        rules.append("shifted yesterday and night not very poor: +0")
    elif extra and shifted_yesterday:
        rules.append(f"shifted yesterday but very poor night (score < {VERY_POOR_SCORE}): allowed")

    final = normal_alarm + timedelta(minutes=extra)
    return {
        "day": normal_alarm.strftime("%Y-%m-%d"),
        "normal_alarm": normal_alarm.strftime("%H:%M"),
        "hard_limit": hard_limit.strftime("%H:%M"),
        "slack_min": slack,
        "night": night,
        "rain": rain,
        "shifted_yesterday": shifted_yesterday,
        "very_poor": very_poor,
        "rules": rules,
        "extra_min": extra,
        "final_alarm": final.strftime("%H:%M"),
    }
