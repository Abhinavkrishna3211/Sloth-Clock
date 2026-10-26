// Radar forwarder for the MR60BHA2 kit (XIAO ESP32C6).
// Reads the radar with the Seeed mmWave library and prints one CSV line per second
// on XIAO D10 for the UNO Q (D0):
//   R,<ms>,<breath_bpm>,<heart_bpm>,<presence 0/1>,<distance_cm>,<movement 0-100>
//
// movement: the radar reports a total phase (chest displacement) several times a second.
// Breathing moves it slowly and by a small, regular amount; turning over or getting up
// moves it a lot. Per 1 s window we take the spread (max - min) of the total phase,
// subtract what quiet breathing produces (PHASE_QUIET), and add the change in distance.
// Both gains are calibration knobs, set by test T1.

#include <Arduino.h>
#include <Seeed_Arduino_mmWave.h>

HardwareSerial mmWaveSerial(0);   // radar, wired inside the kit (D6/D7)
HardwareSerial link(1);           // to the UNO Q
SEEED_MR60BHA2 mmWave;

const int LINK_TX = D10;
const int LINK_RX = D0;           // unused for now, kept free for commands later

const float PHASE_QUIET = 1.5;    // phase spread of quiet breathing (calibrate in T1)
const float PHASE_GAIN = 20.0;    // movement points per unit of extra phase spread
const float DIST_GAIN = 10.0;     // movement points per cm of distance change
const float DIST_TO_CM = 1.0;     // library distance unit -> cm (check with a tape in T0)
const uint32_t PRESENCE_HOLD_MS = 5000;

float breath = 0, heart = 0, distanceCm = 0, lastDistanceCm = 0;
float phaseMin = 1e9, phaseMax = -1e9;
uint32_t lastSeenMs = 0, lastPrintMs = 0;

void setup() {
  Serial.begin(115200);
  link.begin(115200, SERIAL_8N1, LINK_RX, LINK_TX);
  mmWave.begin(&mmWaveSerial);
}

void loop() {
  if (mmWave.update(100)) {
    float total, b, h, v;
    if (mmWave.getHeartBreathPhases(total, b, h)) {
      phaseMin = min(phaseMin, total);
      phaseMax = max(phaseMax, total);
    }
    if (mmWave.getBreathRate(v)) breath = v;
    if (mmWave.getHeartRate(v)) heart = v;
    if (mmWave.getDistance(v)) {
      distanceCm = v * DIST_TO_CM;
      lastSeenMs = millis();
    }
    if (mmWave.isHumanDetected()) lastSeenMs = millis();
  }

  uint32_t now = millis();
  if (now - lastPrintMs < 1000) return;
  lastPrintMs = now;

  bool present = lastSeenMs && now - lastSeenMs < PRESENCE_HOLD_MS;
  float spread = phaseMax > phaseMin ? phaseMax - phaseMin : 0;
  float move = max(0.0f, spread - PHASE_QUIET) * PHASE_GAIN
             + fabsf(distanceCm - lastDistanceCm) * DIST_GAIN;
  int movement = present ? constrain((int)move, 0, 100) : 0;
  lastDistanceCm = distanceCm;
  phaseMin = 1e9;
  phaseMax = -1e9;

  char line[64];
  snprintf(line, sizeof(line), "R,%lu,%.1f,%.1f,%d,%d,%d",
           (unsigned long)now, present ? breath : 0.0f, present ? heart : 0.0f,
           present ? 1 : 0, present ? (int)distanceCm : 0, movement);
  link.println(line);
  Serial.println(line);   // same line on USB for debugging
}
