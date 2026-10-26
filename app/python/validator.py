"""Checks every number and time in a model-written message against the decision record."""
import re

TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*([ap]\.?m\.?)?", re.I)
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
WORDS = {  # "one" is left out: "one tiny step", "no one" are not numbers
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50, "sixty": 60, "hundred": 100,
    "half": None, "quarter": None, "dozen": None,  # vague amounts: never allowed
}
WORD_RE = re.compile(r"\b(" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")\b", re.I)
BANNED = re.compile(r"\bsnooze\b", re.I)
MAX_CHARS = 240


def allowed_values(record):
    """Numeric leaves and HH:MM times anywhere in the record."""
    nums, times = set(), set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            nums.add(round(float(v), 1))
        elif isinstance(v, str):
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
            if m:
                times.add(int(m[1]) * 60 + int(m[2]))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(record)
    return nums, times


def _time_ok(h, m, ampm, times):
    if h > 23 or m > 59:
        return False
    if ampm:
        if h > 12:
            return False
        h = h % 12 + (12 if ampm.lower().startswith("p") else 0)
        return h * 60 + m in times
    return h * 60 + m in times or (h <= 12 and (h % 12 + 12) * 60 + m in times)


def validate(text, record):
    """Returns (ok, problems). Allowed: only numbers and times present in the record."""
    problems = []
    if not text or not text.strip():
        return False, ["empty"]
    if len(text) > MAX_CHARS:
        problems.append(f"too long ({len(text)} chars)")
    if BANNED.search(text):
        problems.append("mentions snooze")
    nums, times = allowed_values(record)

    def check_time(mt):
        if not _time_ok(int(mt[1]), int(mt[2]), mt[3], times):
            problems.append(f"time {mt[0].strip()} not in record")
        return " "

    rest = TIME_RE.sub(check_time, text)  # times first, so 6:45 is not read as 6 and 45
    for n in NUM_RE.findall(rest):  # signs are never parsed: "2-3" is 2 and 3, not -3
        if round(float(n), 1) not in nums:
            problems.append(f"number {n} not in record")
    for w in WORD_RE.findall(rest):
        v = WORDS[w.lower()]
        if v is None or float(v) not in nums:
            problems.append(f"word '{w}' not in record")
    return not problems, problems

