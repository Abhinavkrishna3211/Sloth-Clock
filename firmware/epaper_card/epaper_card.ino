// Sloth Clock e-paper card: XIAO ePaper Display Board EE04 (XIAO ESP32-S3 Plus) + 7.5" 800x480 mono panel.
// POST /show with the card JSON from the UNO Q -> full refresh, then idle. The three keys POST back
// to the UNO Q: KEY0 short = dismiss, KEY0 long (>= 2 s) = step done, KEY1 = next date, KEY2 = refresh.
// Libraries: Seeed_GFX (EPaper class, set the EE04 + 7.5" panel in driver.h), ArduinoJson 7.
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include "secrets.h"  // WIFI_SSID, WIFI_PASS, UNOQ_URL (copy secrets.example.h)

const int KEYS[3] = {2, 3, 5};
const unsigned long LONG_MS = 2000;

EPaper epd;
WebServer server(80);
JsonDocument card;
bool dirty = false;
uint32_t shownAt = 0, renderMs = 0, latencyMs = 0;  // timing of the last refresh, reported on GET /
bool cheer = false;                             // step marked done on the card: the sloth celebrates

// ---------- drawing helpers ----------
float k = 1;                                    // sloth scale
int S(float v) { return (int)lroundf(v * k); }

// Lower half of a circle (a smile, or a closed eye). TFT_eSPI arc angles start at 6 o'clock, clockwise.
void smileArc(int x, int y, int r, int w, uint32_t c, uint32_t bg) {
  epd.drawArc(x, y, r, r - w, 0, 70, c, bg, true);
  epd.drawArc(x, y, r, r - w, 290, 360, c, bg, true);
}
// Filled shapes with a black outline: the sloth is drawn light, outlined, never solid black.
void oEllipse(int x, int y, int rx, int ry, int line = 3) {
  epd.fillEllipse(x, y, rx + line, ry + line, TFT_BLACK);
  epd.fillEllipse(x, y, rx, ry, TFT_WHITE);
}
void oLimb(int ax, int ay, int bx, int by, int w) {
  epd.drawWideLine(ax, ay, bx, by, w + 6, TFT_BLACK, TFT_WHITE);
  epd.drawWideLine(ax, ay, bx, by, w, TFT_WHITE, TFT_BLACK);
}
// Light grey by dithering, for rosy cheeks.
void blush(int x, int y, int rx, int ry) {
  for (int dy = -ry; dy <= ry; dy++)
    for (int dx = -rx; dx <= rx; dx++)
      if ((dx + dy) % 3 == 0 && dx * dx * ry * ry + dy * dy * rx * rx <= rx * rx * ry * ry)
        epd.drawPixel(x + dx, y + dy, TFT_BLACK);
}

// A solid pointed leaf from (x, y) towards angle a (degrees), len long, w wide at the middle.
void leafAt(int x, int y, int len, int w, float a) {
  float c = cosf(a * DEG_TO_RAD), sn = sinf(a * DEG_TO_RAD);
  int px = x, py = y, qx = x, qy = y;
  for (int i = 1; i <= 10; i++) {
    float t = i / 10.0f, h = w * sinf(PI * t), mx = x + c * len * t, my = y + sn * len * t;
    int lx = mx - sn * h, ly = my + c * h, rx = mx + sn * h, ry = my - c * h;
    epd.fillTriangle(px, py, qx, qy, lx, ly, TFT_BLACK);
    epd.fillTriangle(qx, qy, lx, ly, rx, ry, TFT_BLACK);
    px = lx; py = ly; qx = rx; qy = ry;
  }
}
// The vine across the top of the card; everything else hangs from it.
int vineY(int x) { return 22 + (int)lroundf(6 * sinf(x / 50.0f)); }
void drawVine() {
  for (int x = 0; x < 800; x++) epd.fillCircle(x, vineY(x), 2, TFT_BLACK);
  for (int i = 0; i < 20; i++) {                                    // leaves, alternating above and below
    int lx = 14 + i * 40;
    if (lx > 600 && lx < 760) continue;                             // room for the sloth's hands
    leafAt(lx, vineY(lx), 20, 6, i % 2 ? 35 : -35);
  }
}
// A small leaf, used as a bullet.
void leaf(int x, int y) { leafAt(x, y + 3, 15, 5, -30); }

// Soft grey fur on a mono panel: a checkerboard dither inside a black outline.
void fur(int x, int y, int rx, int ry) {
  epd.fillEllipse(x, y, rx + 2, ry + 2, TFT_BLACK);
  epd.fillEllipse(x, y, rx, ry, TFT_WHITE);
  for (int dy = -ry; dy <= ry; dy++)
    for (int dx = -rx; dx <= rx; dx++)
      if (((x + dx + y + dy) & 1) == 0 && dx * dx * ry * ry + dy * dy * rx * rx <= rx * rx * ry * ry)
        epd.drawPixel(x + dx, y + dy, TFT_BLACK);
}
// A furry arm or leg from (ax, ay) to (bx, by), w thick.
void furLimb(int ax, int ay, int bx, int by, int w) {
  epd.drawWideLine(ax, ay, bx, by, w + 4, TFT_BLACK, TFT_WHITE);
  epd.drawWideLine(ax, ay, bx, by, w, TFT_WHITE, TFT_BLACK);
  float vx = bx - ax, vy = by - ay, len2 = vx * vx + vy * vy, r2 = w * w / 4.0f;
  for (int y = min(ay, by) - w; y <= max(ay, by) + w; y++)
    for (int x = min(ax, bx) - w; x <= max(ax, bx) + w; x++) {
      if ((x + y) & 1) continue;
      float t = constrain(((x - ax) * vx + (y - ay) * vy) / len2, 0.0f, 1.0f);
      float dx = ax + t * vx - x, dy = ay + t * vy - y;
      if (dx * dx + dy * dy < r2) epd.drawPixel(x, y, TFT_BLACK);
    }
}
void heart(int x, int y, int r) {
  epd.fillCircle(x - r, y, r, TFT_BLACK);
  epd.fillCircle(x + r, y, r, TFT_BLACK);
  epd.fillTriangle(x - 2 * r, y + r / 2, x + 2 * r, y + r / 2, x, y + 3 * r, TFT_BLACK);
}

enum Mood { SLEEPY, AWAKE, CHEER };
// A small, round sloth hanging from the vine with both arms: big head, little body, white face mask,
// the classic dark eye stripes. x = middle of its head. Its feet are at (x -/+ 18, vineY(x) + 152).
void drawSloth(int x, int mood) {
  int vy = vineY(x), hy = vy + 66, by = hy + 50;
  for (int s = -1; s <= 1; s += 2) {
    int hx = x + s * 30;
    furLimb(x + s * 24, by - 8, hx, vineY(hx) + 4, 13);            // long arms up to the vine
    furLimb(x + s * 12, by + 22, x + s * 18, by + 34, 12);          // little legs
  }
  fur(x, by, 26, 30);                                               // round body
  epd.fillEllipse(x, by + 8, 11, 14, TFT_WHITE);                    // pale tummy
  for (int s = -1; s <= 1; s += 2) fur(x + s * 18, by + 36, 9, 7);  // feet

  fur(x, hy, 38, 34);                                               // big fluffy head
  epd.fillEllipse(x, hy + 5, 30, 24, TFT_WHITE);                    // face mask
  epd.fillEllipse(x, hy - 14, 18, 10, TFT_WHITE);
  for (int s = -1; s <= 1; s += 2) {
    int ex = x + s * 14, ey = hy;
    leafAt(ex - s * 6, ey - 3, 22, 7, s > 0 ? 28 : 152);            // eye stripes, drooping outward
    if (mood == SLEEPY) {
      smileArc(ex, ey - 1, 5, 2, TFT_WHITE, TFT_BLACK);             // closed, peaceful eyes
    } else if (mood == CHEER) {
      epd.drawArc(ex, ey + 3, 5, 3, 120, 240, TFT_WHITE, TFT_BLACK, true);  // ^ ^ happy eyes
    } else {
      epd.fillCircle(ex, ey, 5, TFT_WHITE);                         // shiny eyes
      epd.fillCircle(ex, ey + 1, 3, TFT_BLACK);
      epd.drawPixel(ex - 1, ey - 1, TFT_WHITE);
    }
    blush(x + s * 21, hy + 14, 5, 3);
  }
  epd.fillEllipse(x, hy + 11, 6, 4, TFT_BLACK);                     // button nose
  if (mood == CHEER) {                                              // big open smile
    epd.fillCircle(x, hy + 17, 6, TFT_BLACK);
    epd.fillRect(x - 7, hy + 10, 15, 7, TFT_WHITE);
    epd.fillEllipse(x, hy + 11, 6, 4, TFT_BLACK);
    heart(x - 56, vy + 52, 4);
    heart(x + 54, vy + 74, 3);
    heart(x - 48, vy + 100, 3);
  } else {
    smileArc(x, hy + 15, 6, 2, TFT_BLACK, TFT_WHITE);               // smile
  }
  for (int s = -1; s <= 1; s += 2) {                                // hands hooked over the vine, with claws
    int hx = x + s * 30, cy = vineY(hx);
    fur(hx, cy + 4, 9, 8);
    for (int c = -4; c <= 4; c += 4) epd.drawWideLine(hx + c, cy + 2, hx + c - s * 2, cy - 6, 2, TFT_BLACK, TFT_WHITE);
  }
}

// Night: moon, stars and z z Z. Morning: a smiling sun. (x, y) = where it sits.
void drawSky(int x, int y, bool night) {
  epd.setTextColor(TFT_BLACK, TFT_WHITE);
  if (night) {
    epd.fillCircle(x, y, 14, TFT_BLACK);                           // crescent moon
    epd.fillCircle(x + 7, y - 4, 12, TFT_WHITE);
    const int st[3][2] = {{-26, 26}, {22, 30}, {-8, 52}};          // twinkles
    for (auto &p : st) {
      epd.drawLine(x + p[0] - 4, y + p[1], x + p[0] + 4, y + p[1], TFT_BLACK);
      epd.drawLine(x + p[0], y + p[1] - 4, x + p[0], y + p[1] + 4, TFT_BLACK);
    }
    epd.setFreeFont(&FreeSansBold9pt7b);
    epd.drawString("z", x + 34, y + 58);
    epd.setFreeFont(&FreeSansBold12pt7b);
    epd.drawString("Z", x + 46, y + 36);
  } else {
    int r = 13;
    oEllipse(x, y, r, r, 2);
    for (int a = 0; a < 360; a += 45) {
      float t = a * DEG_TO_RAD;
      epd.drawWideLine(x + (r + 6) * cos(t), y + (r + 6) * sin(t), x + (r + 12) * cos(t), y + (r + 12) * sin(t),
                       3, TFT_BLACK, TFT_WHITE);
    }
    epd.fillCircle(x - 4, y - 2, 2, TFT_BLACK);
    epd.fillCircle(x + 4, y - 2, 2, TFT_BLACK);
    smileArc(x, y + 1, 5, 2, TFT_BLACK, TFT_WHITE);
  }
}

// Draws text in the current font, wrapped to width w, at most maxLines lines; returns the y below.
int wrapped(const String &text, int x, int y, int w, int maxLines) {
  String line, word;
  int lh = epd.fontHeight() + 2, lines = 0;
  for (unsigned i = 0; i <= text.length() && lines < maxLines; i++) {
    char ch = i < text.length() ? text[i] : ' ';
    if (ch != ' ') { word += ch; continue; }
    String next = line.length() ? line + " " + word : word;
    if (epd.textWidth(next) > w && line.length()) {
      epd.drawString(line, x, y);
      y += lh;
      lines++;
      line = word;
    } else {
      line = next;
    }
    word = "";
  }
  if (line.length() && lines < maxLines) { epd.drawString(line, x, y); y += lh; }
  return y;
}

// Shortens text with "..." to fit width w in the current font.
String fit(String s, int w) {
  if (epd.textWidth(s) <= w) return s;
  while (s.length() && epd.textWidth(s + "...") > w) s.remove(s.length() - 1);
  return s + "...";
}

// Month calendar at (x, y), 7 columns of cw px: today in a black box, days with a date circled.
void drawMonth(JsonObject cal, int x, int y, int cw) {
  const int ch = 32;
  const char *wd[7] = {"M", "T", "W", "T", "F", "S", "S"};
  epd.setTextColor(TFT_BLACK, TFT_WHITE);
  epd.setFreeFont(&FreeSansBold18pt7b);
  epd.setTextDatum(TC_DATUM);
  epd.drawString(cal["title"] | "", x + cw * 7 / 2, y);
  epd.setFreeFont(&FreeSansBold12pt7b);
  epd.setTextDatum(MC_DATUM);
  for (int c = 0; c < 7; c++) epd.drawString(wd[c], x + c * cw + cw / 2, y + 44);
  epd.drawLine(x, y + 58, x + cw * 7, y + 58, TFT_BLACK);
  int first = cal["first"] | 0, days = cal["days"] | 30, today = cal["today"] | 0;
  epd.setFreeFont(&FreeSansBold12pt7b);
  for (int d = 1; d <= days; d++) {
    int i = first + d - 1, cx = x + (i % 7) * cw + cw / 2, cy = y + 76 + (i / 7) * ch;
    bool now = d == today, marked = false;
    for (int m : cal["marks"].as<JsonArray>()) marked |= m == d;
    if (now) epd.fillRoundRect(cx - cw / 2 + 1, cy - ch / 2 + 1, cw - 2, ch - 2, 7, TFT_BLACK);
    if (marked) {
      epd.drawCircle(cx, cy, ch / 2, now ? TFT_WHITE : TFT_BLACK);
      epd.drawCircle(cx, cy, ch / 2 - 1, now ? TFT_WHITE : TFT_BLACK);
    }
    epd.setTextColor(now ? TFT_WHITE : TFT_BLACK, now ? TFT_BLACK : TFT_WHITE);
    epd.drawString(String(d), cx, cy);
  }
  epd.setTextDatum(TL_DATUM);
  epd.setTextColor(TFT_BLACK, TFT_WHITE);
}

// ---------- the card ----------
// A vine runs along the top. Left: date, alarm, coming up. Middle: the month. Right: a small sloth hangs
// from the vine and holds today's tiny step on two strings.
void render() {
  uint32_t t = millis();
  epd.fillScreen(TFT_WHITE);
  epd.setTextColor(TFT_BLACK, TFT_WHITE);
  epd.setTextDatum(TL_DATUM);
  bool night = String((const char *)(card["view"] | "night")) == "night";
  const int L = 28, LW = 290;
  drawVine();

  epd.setFreeFont(&FreeSansBold24pt7b);
  epd.drawString(card["date"] | "", L, 44);
  epd.setFreeFont(&FreeSansBold12pt7b);
  epd.drawString(night ? "Tomorrow's alarm" : "Wake up", L, 96);

  String alarm = card["alarm"] | "--:--";           // e.g. "06:45 (+15)": font 8 only has digits and ':'
  int sp = alarm.indexOf(' ');
  String hhmm = sp < 0 ? alarm : alarm.substring(0, sp);
  int y = 124;
  if (hhmm == "off") {
    epd.setFreeFont(&FreeSansBold24pt7b);
    epd.drawString("Off", L, y + 10);
  } else {
    epd.drawString(hhmm, L - 4, y, 8);
  }
  y += 84;
  if (sp > 0) {
    String extra = alarm.substring(sp + 1);         // "(+15)"
    extra.replace("(", "");
    extra.replace(")", "");
    epd.setFreeFont(&FreeSansBold12pt7b);
    epd.drawString(extra + " min of slow morning", L, y);
    y += 30;
  }
  epd.setFreeFont(&FreeSansBold12pt7b);
  epd.drawString(String("never later than ") + (const char *)(card["limit"] | "--:--"), L, y);

  y = 290;
  epd.setFreeFont(&FreeSansBold18pt7b);
  epd.drawString("Coming up", L, y);
  y += 46;
  JsonArray dates = card["dates"].as<JsonArray>();
  epd.setFreeFont(&FreeSansBold12pt7b);
  if (dates.size() == 0) epd.drawString("Nothing soon. Relax.", L, y);
  for (JsonArray d : dates) {
    if (y > 400) break;                              // two fit; the web page has the rest
    leaf(L, y + 10);
    epd.setFreeFont(&FreeSansBold12pt7b);
    epd.drawString(fit(d[1] | "", LW - 24), L + 22, y);
    epd.drawString(d[0] | "", L + 22, y + 28);
    y += 64;
  }
  epd.setFreeFont(&FreeSansBold9pt7b);
  epd.drawString("Hold left key = step done", L, 452);

  if (card["cal"].is<JsonObject>()) drawMonth(card["cal"], 336, 46, 36);

  const int sx = 700, fy = vineY(700) + 152;          // the sloth holds the sign on two strings
  const int bx = 336, bw = 440, byy = 304, bh = 168;
  if (!cheer) drawSky(628, 84, night);
  epd.drawWideLine(sx - 18, fy, sx - 60, byy, 3, TFT_BLACK, TFT_WHITE);
  epd.drawWideLine(sx + 18, fy, sx + 60, byy, 3, TFT_BLACK, TFT_WHITE);
  drawSloth(sx, cheer ? CHEER : night ? SLEEPY : AWAKE);
  epd.fillCircle(sx - 60, byy, 5, TFT_BLACK);                  // pins
  epd.fillCircle(sx + 60, byy, 5, TFT_BLACK);

  epd.drawRoundRect(bx, byy, bw, bh, 14, TFT_BLACK);
  epd.drawRoundRect(bx + 1, byy + 1, bw - 2, bh - 2, 13, TFT_BLACK);
  epd.drawRoundRect(bx + 6, byy + 6, bw - 12, bh - 12, 10, TFT_BLACK);
  epd.setFreeFont(&FreeSansBold12pt7b);
  epd.drawString(cheer ? "Done! Slow and steady." : "Today's tiny step", bx + 20, byy + 16);
  String step = card["step"] | "";
  if (cheer) step = "You did it. Tomorrow's step stays tiny too.";
  int ty = wrapped(step.length() ? step : String("Nothing today. Rest counts too."), bx + 20, byy + 48, bw - 40, 2);
  epd.setFreeFont(&FreeSans12pt7b);
  wrapped(card["message"] | "", bx + 20, ty + 4, bw - 40, 2);

  epd.update();
  epd.sleep();
  renderMs = millis() - t;
  latencyMs = shownAt ? millis() - shownAt : 0;
  shownAt = 0;
}

void onShow() {
  JsonDocument next;
  if (deserializeJson(next, server.arg("plain"))) {
    server.send(400, "text/plain", "bad json");
    return;
  }
  card = next;
  dirty = true;
  shownAt = millis();
  server.send(200, "text/plain", "ok");
}

bool sendKey(const char *key) {
  HTTPClient http;
  http.begin(String(UNOQ_URL) + "/api/card/key");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(String("{\"key\":\"") + key + "\"}");
  http.end();
  return code == 200;
}

void pollKeys() {
  static unsigned long down[3];
  static bool held[3];
  for (int i = 0; i < 3; i++) {
    bool pressed = digitalRead(KEYS[i]) == LOW;
    if (pressed && !held[i]) down[i] = millis();
    if (!pressed && held[i] && millis() - down[i] > 30) {
      const char *key = i == 1 ? "next" : i == 2 ? "refresh" : millis() - down[i] >= LONG_MS ? "done" : "dismiss";
      bool was = cheer;
      if (i != 1) cheer = !strcmp(key, "done");
      if (!sendKey(key) && cheer != was) dirty = true;  // the UNO Q redraws us when it answers
    }
    held[i] = pressed;
  }
}

void setup() {
  for (int k : KEYS) pinMode(k, INPUT_PULLUP);
  epd.begin();
  card["view"] = "night";
  card["message"] = "Connecting...";
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  card["message"] = WiFi.status() == WL_CONNECTED ? "Card address: http://" + WiFi.localIP().toString()
                                                  : String("No Wi-Fi. Check secrets.h.");
  render();
  server.on("/show", HTTP_POST, onShow);
  server.on("/", HTTP_GET, [] {
    server.send(200, "text/plain", "sloth card, last refresh " + String(renderMs) + " ms, POST to done " +
                                   String(latencyMs) + " ms");
  });
  server.begin();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
  server.handleClient();
  pollKeys();
  if (dirty) {
    dirty = false;
    render();
  }
  delay(10);
}
