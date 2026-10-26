// Sloth Clock - real-time side (STM32U585).
// - Reads radar CSV lines on Serial1 (D0), validates them, sends one 10 s summary row
//   over the Bridge.
// - LED matrix: dim sleeping face; sunrise fade on command; full light while ringing.
// - Chime: generated tones on D3 -> PAM8403 -> speaker, every 30 s until dismissed,
//   auto-stop after 10 min.
// - Button on D2 (to GND): short press = dismiss, long press (>= 2 s) = "step done".
//   Dismiss works locally even if the Linux side is busy.
// - Backup alarm: Linux arms the latest wake time every minute. If that time passes and
//   no wake has started (Linux hung or crashed), the MCU rings on its own.
// - Rain microphone (INMP441 on SAI1 block A, off until Linux enables it): 8 blocks of
//   256 samples per second -> RMS, 4 band energies, spectral flatness, impulse count.
//   Only these numbers leave the MCU; samples are never stored or sent.

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

// Sunrise: a glowing sun rises from the bottom edge, grows and brightens, then the sky fills.
// p goes 0 -> 1 over the fade.
void drawSunrise(float p) {
  float rise = p < 0.7f ? p / 0.7f : 1;
  float cy = H + 2.5f - rise * (H - 1.5f);  // sun centre: below the edge -> row 4
  float r = 2.5f + rise;
  float sky = p > 0.6f ? (p - 0.6f) / 0.4f * 4 : 0;
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      float d = sqrtf((x - 6) * (x - 6) + (y - cy) * (y - cy));
      float v = (d <= r ? 7 : 7 - (d - r) * 2.5f) * (0.4f + 0.6f * p);
      if (v < sky) v = sky;
      int level = (int)(v + 0.5f);
      frame[y * W + x] = level < 0 ? 0 : level > 7 ? 7 : level;
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
bool armed = false;  // backup alarm armed
uint32_t phaseStart = 0, sunriseMs = 0, lastChime = 0, lastDraw = 0;
volatile bool startReq = false, stopReq = false, chimeReq = false;
volatile uint32_t reqSunriseS = 600;

// Soft three-note chime, played three times per ring (0 Hz = pause), without blocking the loop.
const int NOTES[][2] = {{1319, 220}, {1047, 220}, {784, 450}, {0, 400},
                        {1319, 220}, {1047, 220}, {784, 450}, {0, 400},
                        {1319, 220}, {1047, 220}, {784, 450}};
const int N_NOTES = sizeof(NOTES) / sizeof(NOTES[0]);
int noteIdx = -1;
uint32_t noteAt = 0;

void startChime() { noteIdx = 0; noteAt = millis(); }

void chimeTick() {
  if (noteIdx < 0 || millis() < noteAt) return;
  if (noteIdx >= N_NOTES) { noTone(CHIME_PIN); noteIdx = -1; return; }
  if (NOTES[noteIdx][0]) tone(CHIME_PIN, NOTES[noteIdx][0], NOTES[noteIdx][1]);
  else noTone(CHIME_PIN);
  noteAt = millis() + NOTES[noteIdx][1] + 60;
  noteIdx++;
}

void endWake(int reason) {  // reason: 3 = dismissed, 4 = timed out, 5 = stopped by Linux
  wake = IDLE;
  armed = false;
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
    } else if (now - lastDraw > 200) {
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

// ---------- backup alarm ----------
volatile bool armReq = false;
volatile int32_t reqArmS = -1;
uint32_t armAt = 0;

void backupTick() {
  if (armed && wake == IDLE && (int32_t)(millis() - armAt) >= 0) {
    armed = false;
    wake = RINGING;
    phaseStart = millis();
    drawFull();
    startChime();
    lastChime = phaseStart;
    Bridge.notify("wake_state", 6);  // 6 = backup alarm fired
  }
}

// ---------- rain microphone (SAI1 block A, register level) ----------
// libm (expf, log10f) reports errors through __errno, which the sketch runtime does not provide.
static int errnoValue;
int *errnoStub() asm("__errno");
int *errnoStub() { return &errnoValue; }

#define REG(a) (*(volatile uint32_t *)(a))
const uint32_t RCC_BASE_A = 0x46020C00, PORTB_A = 0x42020400, PORTC_A = 0x42020800;
const uint32_t SAI1A_A = 0x40015404;  // block A: CR1 +0, CR2 +4, FRCR +8, SLOTR +C, SR +14, DR +1C
const int N = 256, BLOCKS = 8;
float re_[N], im_[N];
volatile bool micReq = false, micOn = false;
bool micReady = false;
uint32_t micSecond = 0;
struct MicAcc { int blocks, samples; float rms, band[4], flat, imp; } mic;

void setAF13(uint32_t port, int pin) {
  REG(port + 0x00) = (REG(port + 0x00) & ~(3u << (pin * 2))) | (2u << (pin * 2));  // MODER = AF
  REG(port + 0x08) |= 3u << (pin * 2);                                             // high speed
  uint32_t afr = port + (pin < 8 ? 0x20 : 0x24);
  int sh = (pin % 8) * 4;
  REG(afr) = (REG(afr) & ~(0xFu << sh)) | (13u << sh);
}

void micInit() {
  REG(RCC_BASE_A + 0x00) |= 1u << 8;                      // HSI16 on
  for (int i = 0; i < 10000 && !(REG(RCC_BASE_A) & (1u << 10)); i++) {}
  REG(RCC_BASE_A + 0xE4) = (REG(RCC_BASE_A + 0xE4) & ~(7u << 5)) | (4u << 5);  // SAI1SEL = HSI16
  REG(RCC_BASE_A + 0x8C) |= (1u << 1) | (1u << 2);        // PORTB_A, PORTC_A clocks
  REG(RCC_BASE_A + 0xA4) |= 1u << 21;                     // SAI1 clock
  setAF13(PORTB_A, 10);  // SCK  (header SCL)
  setAF13(PORTB_A, 9);   // FS   (D10)
  setAF13(PORTC_A, 1);   // SD   (A4)
  REG(SAI1A_A + 0x00) = 0;
  // 64-bit I2S frame, FS active low one bit early, slot 0 (left) only.
  REG(SAI1A_A + 0x08) = 63 | (31u << 8) | (1u << 16) | (1u << 18);
  REG(SAI1A_A + 0x0C) = (1u << 8) | (1u << 16);
  // master receiver, 32-bit data, CKSTR = 1 (sample on rising edge, as the INMP441 needs),
  // NODIV, SCK = 16 MHz / 16 = 1 MHz -> 15.6 kHz sample rate (measured rate is reported).
  REG(SAI1A_A + 0x00) = 1u | (7u << 5) | (1u << 9) | (1u << 19) | (16u << 20);
  REG(SAI1A_A + 0x04) = 1u << 3;  // flush FIFO
  micReady = true;
}

void fft() {  // in-place radix-2, N = 256
  for (int i = 1, j = 0; i < N; i++) {
    int bit = N >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { float t = re_[i]; re_[i] = re_[j]; re_[j] = t; t = im_[i]; im_[i] = im_[j]; im_[j] = t; }
  }
  for (int len = 2; len <= N; len <<= 1) {
    float a = -2 * PI / len;
    for (int i = 0; i < N; i += len)
      for (int k = 0; k < len / 2; k++) {
        float c = cosf(a * k), s = sinf(a * k);
        float xr = re_[i + k + len / 2] * c - im_[i + k + len / 2] * s;
        float xi = re_[i + k + len / 2] * s + im_[i + k + len / 2] * c;
        re_[i + k + len / 2] = re_[i + k] - xr; im_[i + k + len / 2] = im_[i + k] - xi;
        re_[i + k] += xr; im_[i + k] += xi;
      }
  }
}

// Reads one block by polling the FIFO. Gives up after 40 ms (no clock / no mic).
bool readBlock() {
  REG(SAI1A_A + 0x00) |= 1u << 16;  // SAIEN
  uint32_t t0 = millis();
  int n = -16;  // drop the first samples after enable
  while (n < N) {
    if ((REG(SAI1A_A + 0x14) >> 16) & 7) {
      int32_t v = (int32_t)REG(SAI1A_A + 0x1C);
      if (n >= 0) { re_[n] = (v >> 8) / 8388608.0f; im_[n] = 0; }
      n++;
    } else if (millis() - t0 > 40) break;
  }
  REG(SAI1A_A + 0x00) &= ~(1u << 16);
  REG(SAI1A_A + 0x04) = 1u << 3;
  return n == N;
}

void analyseBlock() {
  float mean = 0, e = 0;
  for (int i = 0; i < N; i++) mean += re_[i];
  mean /= N;
  float sub[8] = {0};
  for (int i = 0; i < N; i++) {
    re_[i] -= mean;
    e += re_[i] * re_[i];
    sub[i / 32] += re_[i] * re_[i];
  }
  float sorted[8];
  memcpy(sorted, sub, sizeof(sub));
  for (int i = 1; i < 8; i++) for (int j = i; j && sorted[j] < sorted[j - 1]; j--) {
    float t = sorted[j]; sorted[j] = sorted[j - 1]; sorted[j - 1] = t;
  }
  for (int i = 0; i < 8; i++) if (sub[i] > 6 * sorted[3] + 1e-12f) mic.imp++;
  for (int i = 0; i < N; i++) re_[i] *= 0.5f - 0.5f * cosf(2 * PI * i / (N - 1));  // Hann
  fft();
  // bands at fs ~15.6 kHz, 61 Hz per bin: 0.5-1, 1-2, 2-4, 4-7.8 kHz
  const int edges[5] = {8, 16, 33, 66, 128};
  float logSum = 0, lin = 0;
  for (int k = 1; k < N / 2; k++) {
    float p = re_[k] * re_[k] + im_[k] * im_[k] + 1e-20f;
    logSum += logf(p);
    lin += p;
    for (int b = 0; b < 4; b++) if (k >= edges[b] && k < edges[b + 1]) mic.band[b] += p;
  }
  mic.flat += expf(logSum / (N / 2 - 1)) / (lin / (N / 2 - 1));
  mic.rms += sqrtf(e / N);
  mic.blocks++;
}

int db10(float x) { return (int)(100 * log10f(x + 1e-12f)); }

void micTick() {
  if (micReq && !micReady) micInit();
  micOn = micReq;
  if (!micOn) return;
  uint32_t now = millis();
  if (mic.samples < BLOCKS && now - micSecond < 1000) {
    if (readBlock()) analyseBlock();
    mic.samples++;  // attempts
  }
  if (now - micSecond >= 1000) {
    int b = mic.blocks;
    // mic_row: blocks ok, rms dBFS x10, 4 band dB x10, flatness x1000, impulses per block x100
    Bridge.notify("mic_row", b, b ? db10(mic.rms / b) * 2 : 0,
                  b ? db10(mic.band[0] / b) : 0, b ? db10(mic.band[1] / b) : 0,
                  b ? db10(mic.band[2] / b) : 0, b ? db10(mic.band[3] / b) : 0,
                  b ? (int)(mic.flat / b * 1000) : 0, b ? (int)(mic.imp * 100 / b) : 0);
    memset(&mic, 0, sizeof(mic));
    micSecond = now;
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
void backup_arm(int seconds) {  // < 0 disarms
  k_mutex_lock(&mtx, K_FOREVER);
  reqArmS = seconds;
  armReq = true;
  k_mutex_unlock(&mtx);
}
void mic_enable(bool on) { micReq = on; }

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
  if (armReq) {
    armReq = false;
    armed = reqArmS >= 0;
    armAt = millis() + (uint32_t)(reqArmS < 0 ? 0 : reqArmS) * 1000UL;
  }
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
  Bridge.provide("backup_arm", backup_arm);
  Bridge.provide("mic_enable", mic_enable);
  rowStart = millis();
}

void loop() {
  readRadar();
  handleRequests();
  wakeTick();
  chimeTick();
  buttonTick();
  backupTick();
  micTick();
  if (millis() - rowStart >= ROW_MS) {
    rowStart += ROW_MS;
    sendRow();
  }
  delay(2);
}
