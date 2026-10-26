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

// A sloth from circles and arcs, hanging from a branch. (x, y) = centre of the head.
void drawSloth(int x, int y, bool asleep) {
  epd.drawLine(x - 90, y - 70, x + 90, y - 70, TFT_BLACK);
  epd.drawLine(x - 90, y - 69, x + 90, y - 69, TFT_BLACK);
  epd.drawLine(x - 30, y - 69, x - 25, y - 30, TFT_BLACK);  // arms up to the branch
  epd.drawLine(x + 30, y - 69, x + 25, y - 30, TFT_BLACK);
  epd.drawCircle(x, y, 40, TFT_BLACK);                       // head
  epd.drawEllipse(x, y + 5, 30, 22, TFT_BLACK);              // face mask
  for (int s = -1; s <= 1; s += 2) {
    epd.fillEllipse(x + s * 14, y, 9, 6, TFT_BLACK);         // eye patches
    if (asleep) epd.drawLine(x + s * 14 - 5, y, x + s * 14 + 5, y, TFT_WHITE);
    else epd.fillCircle(x + s * 14, y, 2, TFT_WHITE);
  }
  epd.fillCircle(x, y + 10, 3, TFT_BLACK);                   // nose
  epd.drawArc(x, y + 14, 8, 7, 30, 150, TFT_BLACK, TFT_WHITE); // smile
}

void render() {
  epd.fillScreen(TFT_WHITE);
  epd.setTextColor(TFT_BLACK, TFT_WHITE);
  bool night = String((const char *)(card["view"] | "night")) == "night";
  drawSloth(680, 130, night);

  epd.setTextDatum(TL_DATUM);
  epd.drawString(card["date"] | "", 30, 30, 4);
  epd.drawString("Alarm", 30, 90, 4);
  epd.drawString(card["alarm"] | "--:--", 30, 125, 7);
  epd.drawString(String("must be up by ") + (const char *)(card["limit"] | "--:--"), 30, 210, 2);

  int y = 260;
  epd.drawString("Coming up", 30, y, 4);
  for (JsonArray d : card["dates"].as<JsonArray>()) {
    y += 34;
    epd.drawString(String((const char *)(d[0] | "")) + "  " + (const char *)(d[1] | ""), 40, y, 2);
  }
  if (card["dates"].as<JsonArray>().size() == 0) epd.drawString("Nothing soon.", 40, y + 34, 2);

  epd.drawLine(30, 400, 770, 400, TFT_BLACK);
  epd.drawString(String("Today: ") + (const char *)(card["step"] | ""), 30, 412, 2);
  epd.drawString(card["message"] | "", 30, 444, 2);
  epd.update();
  epd.sleep();
}

void onShow() {
  JsonDocument next;
  if (deserializeJson(next, server.arg("plain"))) {
    server.send(400, "text/plain", "bad json");
    return;
  }
  card = next;
  dirty = true;
  server.send(200, "text/plain", "ok");
}

void sendKey(const char *key) {
  HTTPClient http;
  http.begin(String(UNOQ_URL) + "/api/card/key");
  http.addHeader("Content-Type", "application/json");
  http.POST(String("{\"key\":\"") + key + "\"}");
  http.end();
}

void pollKeys() {
  static unsigned long down[3];
  static bool held[3];
  for (int i = 0; i < 3; i++) {
    bool pressed = digitalRead(KEYS[i]) == LOW;
    if (pressed && !held[i]) down[i] = millis();
    if (!pressed && held[i] && millis() - down[i] > 30) {
      if (i == 0) sendKey(millis() - down[i] >= LONG_MS ? "done" : "dismiss");
      else sendKey(i == 1 ? "next" : "refresh");
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
  server.on("/", HTTP_GET, [] { server.send(200, "text/plain", "sloth card"); });
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
