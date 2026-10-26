// Sloth Clock - real-time side (STM32U585).
// - Reads radar CSV lines on Serial1 (D0), validates them, sends one 10 s summary row
//   over the Bridge.
// - LED matrix: dim sleeping face; sunrise fade on command; full light while ringing.
// - Chime: generated tones on D3 -> PAM8403 -> speaker, every 30 s until dismissed,
//   auto-stop after 10 min.
// - Button on D2 (to GND): short press = dismiss, long press (>= 2 s) = "step done".
//   Dismiss works locally even if the Linux side is busy.

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <zephyr/kernel.h>

const int CHIME_PIN = 3;
const int BUTTON_PIN = 2;
const uint32_t ROW_MS = 10000;
const uint32_t CHIME_EVERY_MS = 30000;
const uint32_t RING_MAX_MS = 10UL * 60 * 1000;
const uint32_t LONG_PRESS_MS = 2000;
const int W = 13, H = 8;

Arduino_LED_Matrix matrix;
K_MUTEX_DEFINE(mtx);  // Bridge providers run on another thread

// ---------- radar rows ----------
struct Acc {
  int lines, bad, present, breathN, heartN, distN, moveMax;
  float breathSum, heartSum, distSum, moveSum;
} acc;
uint32_t rowStart = 0;
char lineBuf[96];
int lineLen = 0;
char injected[96];
bool hasInjected = false;

// Validates "R,<ms>,<breath>,<heart>,<presence>,<distance_cm>,<movement>".
bool parseLine(const char *s) {
  if (s[0] != 'R' || s[1] != ',') return false;
  unsigned long ms;
  float breath, heart;
  int presence, dist, move;
  char tail;
  if (sscanf(s + 2, "%lu,%f,%f,%d,%d,%d%c", &ms, &breath, &heart, &presence, &dist, &move, &tail) != 6)
    return false;
  if (breath < 0 || breath > 60 || heart < 0 || heart > 200 || presence < 0 || presence > 1 ||
      dist < 0 || dist > 600 || move < 0 || move > 100)
    return false;
  acc.lines++;
  if (presence) {
    acc.present++;
    if (breath > 0) { acc.breathSum += breath; acc.breathN++; }
    if (heart > 0) { acc.heartSum += heart; acc.heartN++; }
    if (dist > 0) { acc.distSum += dist; acc.distN++; }
  }
  acc.moveSum += move;
  if (move > acc.moveMax) acc.moveMax = move;
  return true;
}

void handleLine(const char *s) {
  if (!parseLine(s)) acc.bad++;
}

void readRadar() {
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\r') continue;
    if (c == '\n') {
      lineBuf[lineLen] = 0;
      if (lineLen) handleLine(lineBuf);
      lineLen = 0;
    } else if (lineLen < (int)sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineLen = 0;  // overlong line: drop it
      acc.bad++;
    }
  }
}

void sendRow() {
  // radar_row: lines, bad, presence %, breath x10, heart x10, distance cm, movement max, movement mean x10
  int n = acc.lines;
  Bridge.notify("radar_row", n, acc.bad,
                n ? acc.present * 100 / n : 0,
                acc.breathN ? (int)(acc.breathSum * 10 / acc.breathN) : 0,
                acc.heartN ? (int)(acc.heartSum * 10 / acc.heartN) : 0,
                acc.distN ? (int)(acc.distSum / acc.distN) : 0,
                acc.moveMax,
                n ? (int)(acc.moveSum * 10 / n) : 0);
  memset(&acc, 0, sizeof(acc));
}

// ---------- LED matrix ----------
uint8_t frame[W * H];
const uint8_t FACE[H][W + 1] = {
  ".............",
  ".............",
  ".X..X...X..X.",
  "..XX.....XX..",
  ".............",
  ".....X.X.....",
  "......X......",
  ".............",
};

void drawFace() {
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++)
      frame[y * W + x] = FACE[y][x] == 'X' ? 1 : 0;  // level 1 of 7: barely glows
  matrix.draw(frame);
}

// Sunrise: pixels light from the bottom up, in a scattered order, and brighten.
// p goes 0 -> 1 over the fade.
void drawSunrise(float p) {
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      float noise = ((x * 7 + y * 13) % 17) / 17.0f;
      float t = (H - 1 - y) / (float)H * 0.6f + noise * 0.4f;
      int level = 0;
      if (p > t) level = 1 + (int)((p - t) / (1.0f - t + 0.001f) * 6);
      frame[y * W + x] = level > 7 ? 7 : level;
    }
  matrix.draw(frame);
}

void drawFull() {
  memset(frame, 7, sizeof(frame));
  matrix.draw(frame);
}

// ---------- wake state ----------
enum WakeState { IDLE, SUNRISE, RINGING };
volatile WakeState wake = IDLE;
uint32_t phaseStart = 0, sunriseMs = 0, lastChime = 0, lastDraw = 0;
volatile bool startReq = false, stopReq = false, chimeReq = false;
volatile uint32_t reqSunriseS = 600;

// Soft three-note chime, played without blocking the loop.
const int NOTES[][2] = {{1319, 220}, {1047, 220}, {784, 450}};
int noteIdx = -1;
uint32_t noteAt = 0;

void startChime() { noteIdx = 0; noteAt = millis(); }

void chimeTick() {
  if (noteIdx < 0 || millis() < noteAt) return;
  if (noteIdx >= 3) { noTone(CHIME_PIN); noteIdx = -1; return; }
  tone(CHIME_PIN, NOTES[noteIdx][0], NOTES[noteIdx][1]);
  noteAt = millis() + NOTES[noteIdx][1] + 60;
  noteIdx++;
}

void endWake(int reason) {  // reason: 3 = dismissed, 4 = timed out, 5 = stopped by Linux
  wake = IDLE;
  noteIdx = -1;
  noTone(CHIME_PIN);
  drawFace();
  Bridge.notify("wake_state", reason);
}

void wakeTick() {
  uint32_t now = millis();
  if (wake == SUNRISE) {
    float p = sunriseMs ? (now - phaseStart) / (float)sunriseMs : 1;
    if (p >= 1) {
      wake = RINGING;
      phaseStart = now;
      drawFull();
      startChime();
      lastChime = now;
      Bridge.notify("wake_state", 2);
    } else if (now - lastDraw > 1000) {
      drawSunrise(p);
      lastDraw = now;
    }
  } else if (wake == RINGING) {
    if (now - phaseStart > RING_MAX_MS) endWake(4);
    else if (now - lastChime > CHIME_EVERY_MS) { startChime(); lastChime = now; }
  }
}

// ---------- button ----------
bool btnDown = false, longSent = false;
uint32_t btnSince = 0, btnChange = 0;

void buttonTick() {
  bool down = digitalRead(BUTTON_PIN) == LOW;
  uint32_t now = millis();
  if (down != btnDown && now - btnChange > 30) {  // 30 ms debounce
    btnChange = now;
    btnDown = down;
    if (down) { btnSince = now; longSent = false; }
    else if (!longSent) {
      if (wake != IDLE) endWake(3);
      Bridge.notify("button", 0);
    }
  }
  if (btnDown && !longSent && now - btnSince >= LONG_PRESS_MS) {
    longSent = true;
    Bridge.notify("button", 1);
  }
}

// ---------- Bridge providers (other thread: only set flags) ----------
void wake_start(int sunrise_s) {
  k_mutex_lock(&mtx, K_FOREVER);
  reqSunriseS = sunrise_s < 0 ? 0 : sunrise_s;
  startReq = true;
  k_mutex_unlock(&mtx);
}

void wake_stop() { stopReq = true; }
void chime_test() { chimeReq = true; }

void inject_line(String s) {  // feeds a radar line without the radar (tests)
  k_mutex_lock(&mtx, K_FOREVER);
  strncpy(injected, s.c_str(), sizeof(injected) - 1);
  injected[sizeof(injected) - 1] = 0;
  hasInjected = true;
  k_mutex_unlock(&mtx);
}

void handleRequests() {
  k_mutex_lock(&mtx, K_FOREVER);
  if (hasInjected) { handleLine(injected); hasInjected = false; }
  bool start = startReq;
  uint32_t s = reqSunriseS;
  startReq = false;
  k_mutex_unlock(&mtx);

  if (start) {
    wake = SUNRISE;
    sunriseMs = s * 1000UL;
    phaseStart = millis();
    lastDraw = 0;
    Bridge.notify("wake_state", 1);
  }
  if (stopReq) { stopReq = false; if (wake != IDLE) endWake(5); }
  if (chimeReq) { chimeReq = false; startChime(); }
}

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(CHIME_PIN, OUTPUT);
  matrix.begin();
  matrix.setGrayscaleBits(3);  // levels 0..7
  drawFace();
  Serial1.begin(115200);

  Bridge.begin();
  Bridge.provide("wake_start", wake_start);
  Bridge.provide("wake_stop", wake_stop);
  Bridge.provide("chime_test", chime_test);
  Bridge.provide("inject_line", inject_line);
  rowStart = millis();
}

void loop() {
  readRadar();
  handleRequests();
  wakeTick();
  chimeTick();
  buttonTick();
  if (millis() - rowStart >= ROW_MS) {
    rowStart += ROW_MS;
    sendRow();
  }
  delay(2);
}
