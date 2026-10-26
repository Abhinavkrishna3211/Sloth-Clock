"""SQLite storage. Only small feature rows, settings, events and decision records."""
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS rows (
  ts REAL PRIMARY KEY, lines INT, bad INT, presence INT,
  breath REAL, heart REAL, distance INT, move_max INT, move_mean REAL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS events (ts REAL, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS decisions (day TEXT PRIMARY KEY, ts REAL, record TEXT, message TEXT);
"""


class Store:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.executescript(SCHEMA)

    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args)]

    def add_row(self, r, ts=None):
        self._exec("INSERT OR REPLACE INTO rows VALUES (?,?,?,?,?,?,?,?,?)",
                   (ts or time.time(), r["lines"], r["bad"], r["presence"], r["breath"],
                    r["heart"], r["distance"], r["move_max"], r["move_mean"]))

    def rows_since(self, ts):
        return self._all("SELECT * FROM rows WHERE ts >= ? ORDER BY ts", (ts,))

    def get_settings(self, defaults):
        s = dict(defaults)
        s.update({r["key"]: r["value"] for r in self._all("SELECT * FROM settings")})
        return s

    def set_setting(self, key, value):
        self._exec("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))

    def event(self, kind, detail=""):
        self._exec("INSERT INTO events VALUES (?,?,?)", (time.time(), kind, detail))

    def events_since(self, ts):
        return self._all("SELECT * FROM events WHERE ts >= ? ORDER BY ts", (ts,))

    def save_decision(self, day, record, message=None):
        self._exec("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?)",
                   (day, time.time(), json.dumps(record), message))

    def set_message(self, day, message):
        self._exec("UPDATE decisions SET message = ? WHERE day = ?", (message, day))

    def decision(self, day):
        r = self._all("SELECT * FROM decisions WHERE day = ?", (day,))
        if not r:
            return None
        return {"day": day, "ts": r[0]["ts"], "record": json.loads(r[0]["record"]), "message": r[0]["message"]}

    def last_decision(self):
        r = self._all("SELECT day FROM decisions ORDER BY ts DESC LIMIT 1")
        return self.decision(r[0]["day"]) if r else None
