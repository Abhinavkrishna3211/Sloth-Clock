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
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, title TEXT, due TEXT, kind TEXT, steps TEXT, created REAL, done INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS mornings (
  day TEXT PRIMARY KEY, item INT, size TEXT, step TEXT, features TEXT, info TEXT, done INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS mic (
  ts REAL PRIMARY KEY, blocks INT, rms INT, b1 INT, b2 INT, b3 INT, b4 INT, flat INT, imp INT);
CREATE TABLE IF NOT EXISTS rain_labels (ts REAL PRIMARY KEY, x TEXT, rain INT);
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

    # ---------- dates and jobs ----------
    def items(self):
        rows = self._all("SELECT * FROM items ORDER BY id")
        for r in rows:
            r["steps"] = json.loads(r["steps"]) if r["steps"] else None
        return rows

    def add_item(self, title, due, kind, steps=None):
        return self._exec("INSERT INTO items (title, due, kind, steps, created) VALUES (?,?,?,?,?)",
                          (title, due, kind, json.dumps(steps) if steps else None, time.time())).lastrowid

    def set_steps(self, item_id, steps):
        self._exec("UPDATE items SET steps = ? WHERE id = ?", (json.dumps(steps), item_id))

    def set_item_done(self, item_id, done=1):
        self._exec("UPDATE items SET done = ? WHERE id = ?", (done, item_id))

    def delete_item(self, item_id):
        self._exec("DELETE FROM items WHERE id = ?", (item_id,))

    # ---------- one tiny step a day ----------
    def morning(self, day):
        r = self._all("SELECT * FROM mornings WHERE day = ?", (day,))
        if not r:
            return None
        r = r[0]
        r["features"], r["info"] = json.loads(r["features"]), json.loads(r["info"])
        return r

    def save_morning(self, day, item, size, step, features, info):
        self._exec("INSERT OR REPLACE INTO mornings VALUES (?,?,?,?,?,?,0)",
                   (day, item, size, step, json.dumps(features), json.dumps(info)))

    def set_morning_done(self, day):
        self._exec("UPDATE mornings SET done = 1 WHERE day = ?", (day,))

    def history(self, before_day):
        """(features, done) for every past morning: the predictor's training rows."""
        return [(json.loads(r["features"]), r["done"]) for r in
                self._all("SELECT features, done FROM mornings WHERE day < ? ORDER BY day", (before_day,))]

    # ---------- rain ----------
    def add_mic(self, r):
        self._exec("INSERT OR REPLACE INTO mic VALUES (?,?,?,?,?,?,?,?,?)",
                   (r["ts"], r["blocks"], r["rms"], r["b1"], r["b2"], r["b3"], r["b4"], r["flat"], r["imp"]))

    def mic_since(self, ts):
        return self._all("SELECT * FROM mic WHERE ts >= ? ORDER BY ts", (ts,))

    def add_rain_label(self, x, rain):
        self._exec("INSERT OR REPLACE INTO rain_labels VALUES (?,?,?)", (time.time(), json.dumps(x), int(rain)))

    def rain_labels(self):
        return [(json.loads(r["x"]), bool(r["rain"])) for r in self._all("SELECT x, rain FROM rain_labels")]
