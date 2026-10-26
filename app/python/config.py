"""All tunable values in one place."""
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REAL_DB = DATA_DIR / "real.sqlite"
DEMO_DB = DATA_DIR / "demo.sqlite"

# Night score (spec F1). Each term is a share of the observed minutes (0-100 %),
# so a short demo nap and a full night are scored on the same scale.
# score = 100 - (W_RESTLESS * restless_% + W_IRREGULAR * irregular_% + W_LONG_AWAKE * long_awakenings)
W_RESTLESS = 1.0
W_IRREGULAR = 0.5
W_LONG_AWAKE = 10.0
MOVE_THRESHOLD = 30        # movement level (0-100) that makes a minute restless
BREATH_STD_THRESHOLD = 3.0 # bpm; breath-rate std over 2 min above this = irregular
LONG_AWAKE_MIN = 10        # continuous minutes of movement / out of bed
PRESENT_PCT = 50           # a 10 s row counts as "in bed" at or above this presence %
MIN_COVERAGE = 0.7         # share of expected rows that must arrive for a confident score
MIN_MINUTES_REAL = 60
MIN_MINUTES_DEMO = 5
NIGHT_HOURS = 10           # rows from this many hours before the alarm form the night

# Alarm (spec F2). Health limits are hard-coded in decision.py, not here.
DECISION_LEAD_MIN = 45
SUNRISE_S = 600
DEMO_SUNRISE_S = 60
DEMO_DEFAULT_MIN = 15
DEFAULT_SETTINGS = {"normal_alarm": "06:30", "hard_limit": "07:00", "enabled": "1"}

# Wake message (spec F3)
LLM_URL = "http://msgpack-rpc-router:8080"  # the host, as seen from the app container
LLM_TIMEOUT_S = 90
