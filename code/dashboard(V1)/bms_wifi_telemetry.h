/*
 * bms_wifi_telemetry.h
 * ESP32 WiFi Telemetry Module — Real-Device Mode
 *
 * Posts live BMS readings from the ESP32 to the Python dashboard server
 * every 2 seconds via HTTP POST to /api/telemetry.
 *
 * SETUP INSTRUCTIONS:
 *   1. Set WIFI_SSID and WIFI_PASS to your network credentials.
 *   2. Set SERVER_TELEMETRY_URL to your PC's local IP (shown when server.py starts).
 *      Example: "http://192.168.1.55:8000/api/telemetry"
 *   3. Flash to ESP32 and open Serial Monitor at 115200 baud.
 *      The ESP32 will print its own IP and confirm POSTs succeed.
 */

#ifndef BMS_WIFI_TELEMETRY_H
#define BMS_WIFI_TELEMETRY_H

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ─── USER CONFIGURATION — CHANGE THESE ───────────────────────────────────────
const char* WIFI_SSID = "JioFiber-yogesh";       // Your WiFi network name
const char* WIFI_PASS = "13011965";   // Your WiFi password

// IP address of your PC running server.py (shown in server.py startup log)
// Example: "http://192.168.1.55:8000/api/telemetry"
const char* SERVER_TELEMETRY_URL = "http://192.168.29.156:8000/api/telemetry";

// Minimum cell voltage considered "real" (not floating ADC noise)
// Cells below this are treated as disconnected
const float MIN_VALID_CELL_VOLTAGE = 2.5;
// ──────────────────────────────────────────────────────────────────────────────

// ─── External variables from bms.ino ─────────────────────────────────────────
extern bool config_mode;
extern float raw_cell_volt[];
extern float cell_volt[];
extern float soc;
extern float soh[];
extern String health_status[];
extern float internal_resistance[];
extern bool charging;
extern bool load_state;
extern float cycle_count;
extern float current_bleed[];
extern float read_voltage();
extern float b_read_voltage();
extern float read_current();
extern float get_true_charge_current();
// ──────────────────────────────────────────────────────────────────────────────

// ─── Battery Connection Detection ─────────────────────────────────────────────
// Returns true only when ALL cell voltages are above the minimum threshold.
// This prevents floating/noise ADC readings from being treated as a connected battery.
bool is_battery_connected() {
  for (int i = 0; i < 3; i++) {
    if (raw_cell_volt[i] < MIN_VALID_CELL_VOLTAGE) {
      return false;
    }
  }
  return true;
}
// ──────────────────────────────────────────────────────────────────────────────

// ─── Build JSON Telemetry Payload ─────────────────────────────────────────────
String get_telemetry_json() {
  StaticJsonDocument<1024> doc;

  bool battery_ok = is_battery_connected();

  doc["connected"] = battery_ok;

  if (!battery_ok) {
    // Battery not connected — send zeros and empty cells array
    doc["cellCount"]      = 0;
    doc["series"]         = 0;
    doc["parallel"]       = 0;
    doc["configuration"]  = "--";
    doc["batteryVoltage"] = 0.0;
    doc["inputVoltage"]   = 0.0;
    doc["current"]        = 0.0;
    doc["soc"]            = 0.0;
    doc["soh"]            = 0.0;
    doc.createNestedArray("cells");
  } else {
    // Battery connected — send real measurements
    doc["cellCount"]      = 3;
    doc["series"]         = 3;
    doc["parallel"]       = 1;
    doc["configuration"]  = config_mode ? "3S1P" : "3P1S";
    doc["batteryVoltage"] = b_read_voltage();
    doc["inputVoltage"]   = read_voltage();
    doc["current"]        = read_current();
    doc["soc"]            = soc;

    float total_soh = 0.0;
    JsonArray cells_arr = doc.createNestedArray("cells");

    for (int i = 0; i < 3; i++) {
      JsonObject cell = cells_arr.createNestedObject();
      cell["id"]      = i + 1;
      cell["voltage"] = raw_cell_volt[i];

      // Per-cell SOC derived from OCV curve (linear approximation 3.0V–4.2V)
      float c_soc = (raw_cell_volt[i] - 3.0f) / (4.2f - 3.0f) * 100.0f;
      c_soc = constrain(c_soc, 0.0f, 100.0f);
      cell["soc"] = c_soc;

      cell["soh"]    = soh[i];
      total_soh     += soh[i];
      cell["temp"]   = 25.0f; // Replace with real sensor value when available
      cell["health"] = health_status[i];
      cell["ir"]     = internal_resistance[i] * 1000.0f; // Ohms → mΩ
      cell["bleed"]  = current_bleed[i];
    }

    doc["soh"] = total_soh / 3.0f;
  }

  String json_output;
  serializeJson(doc, json_output);
  return json_output;
}
// ──────────────────────────────────────────────────────────────────────────────

// ─── WiFi Init ────────────────────────────────────────────────────────────────
void init_wifi_telemetry() {
  Serial.println("\n[WiFi] Connecting to: " + String(WIFI_SSID));
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected!");
    Serial.print("[WiFi] ESP32 IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("[WiFi] Posting telemetry to: ");
    Serial.println(SERVER_TELEMETRY_URL);
  } else {
    Serial.println("\n[WiFi] Connection FAILED — check SSID/password.");
    Serial.println("[WiFi] Continuing without WiFi. Serial data only.");
  }
}
// ──────────────────────────────────────────────────────────────────────────────

// ─── Telemetry Upload Loop (call from loop()) ─────────────────────────────────
void update_wifi_telemetry() {
  if (WiFi.status() != WL_CONNECTED) return;

  static unsigned long last_post_ms = 0;
  unsigned long now = millis();

  // POST every 2 seconds
  if (now - last_post_ms < 2000) return;
  last_post_ms = now;

  String json_data = get_telemetry_json();

  HTTPClient http;
  http.begin(SERVER_TELEMETRY_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(3000); // 3 second timeout

  int httpCode = http.POST(json_data);

  if (httpCode == 200) {
    Serial.printf("[Telemetry] POST OK | connected=%s | Vbat=%.2fV | SOC=%.1f%%\n",
                  is_battery_connected() ? "true" : "false",
                  b_read_voltage(),
                  soc);
  } else if (httpCode > 0) {
    Serial.printf("[Telemetry] POST failed, HTTP code: %d\n", httpCode);
  } else {
    Serial.printf("[Telemetry] POST error: %s\n", http.errorToString(httpCode).c_str());
    // Try to reconnect WiFi if connection dropped
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WiFi] Reconnecting...");
      WiFi.reconnect();
    }
  }

  http.end();
}
// ──────────────────────────────────────────────────────────────────────────────

#endif // BMS_WIFI_TELEMETRY_H
