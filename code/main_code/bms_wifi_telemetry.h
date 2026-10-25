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

#ifndef PARALLEL
#define PARALLEL 0
#endif
#ifndef SERIES
#define SERIES 1
#endif

// ─── USER CONFIGURATION — CHANGE THESE ───────────────────────────────────────
const char* WIFI_SSID = "YOGA";       // Your WiFi network name
const char* WIFI_PASS = "12345678";   // Your WiFi password

// IP address of your PC running server.py (shown in server.py startup log)
// Example: "http://192.168.1.55:8000/api/telemetry"
const char* SERVER_TELEMETRY_URL = "http://10.102.48.178:8000/api/telemetry";

// Minimum cell voltage considered "real" (not floating ADC noise)
// Cells below this are treated as disconnected.
// 2.0V gives a safe margin below the deepest discharge limit (3.0V) while
// still rejecting genuine floating ADC readings (~0V when no cell attached).
const float MIN_VALID_CELL_VOLTAGE = 2.0;
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
extern float capacity_ah;
extern float read_voltage();
extern float b_read_voltage();
extern float read_current();
extern float get_true_charge_current();

// User configurable settings stored in Preferences
#include <Preferences.h>
extern Preferences preferences;
extern int user_charging_mode;
extern int user_discharge_mode;
extern float user_capacity;
extern float user_max_voltage_cell;
extern float user_cutoff_current;
extern volatile bool config_updated;

// Guard flag: set true during WiFi TX burst to freeze current readings.
// The ESP32 WiFi radio draws ~250mA during TX, which droops the 3.3V rail
// and shifts the ACS712's VCC/2 zero-point — causing false current spikes.
bool wifi_tx_active = false;

// When true, the BMS is in the CV termination phase and current taper is
// the sole end-of-charge signal. Telemetry uploads are blocked to prevent
// TX bursts from causing premature charge termination.
extern bool cv_phase_critical;
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
  StaticJsonDocument<1536> doc;

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
    doc["charging"]       = false;
    doc["discharging"]    = false;
    doc["load_state"]     = false;
    doc["mode"]           = "DISCONNECTED";
    doc.createNestedArray("cells");
  } else {
    // Battery connected — send real measurements
    doc["cellCount"]      = 3;

    // Build topology strings from actual configured modes:
    // SERIES (1) → cells in series  → e.g. "3S1P"  (3 series, 1 parallel)
    // PARALLEL(0) → cells in parallel → e.g. "1S3P"  (1 series, 3 parallel)
    String chg_topo  = (user_charging_mode  == SERIES) ? "3S1P" : "1S3P";
    String dis_topo  = (user_discharge_mode == SERIES) ? "3S1P" : "1S3P";

    // Active topology = whichever mode the pack is currently operating in.
    // Use actual firmware operating state (charging / load_state) rather than
    // raw current which can drift positive by ~0.15A due to ACS712 sensor noise.
    float cur = read_current();
    String active_topo = dis_topo;
    if (charging) {
      active_topo = chg_topo;
    } else if (load_state) {
      active_topo = dis_topo;
    } else {
      active_topo = (cur > 0.25f) ? chg_topo : dis_topo;
    }

    doc["series"]            = (user_charging_mode == SERIES) ? 3 : 1;
    doc["parallel"]          = (user_charging_mode == SERIES) ? 1 : 3;
    doc["configuration"]     = active_topo;     // Active topology string shown in header
    doc["charge_topology"]   = chg_topo;        // Always send both so dashboard can show both
    doc["discharge_topology"]= dis_topo;

    doc["batteryVoltage"] = b_read_voltage();
    doc["inputVoltage"]   = read_voltage();
    doc["current"]        = cur;
    doc["soc"]            = soc;
    doc["charging"]       = charging;
    doc["discharging"]    = load_state;
    doc["load_state"]     = load_state;
    doc["mode"]           = charging ? "CHARGING" : (load_state ? "DISCHARGING" : "IDLE");

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

  // Always append current ESP32 config state so dashboard can populate UI inputs
  JsonObject confObj = doc.createNestedObject("esp32_config");
  confObj["charge_mode"] = user_charging_mode;
  confObj["discharge_mode"] = user_discharge_mode;
  confObj["capacity"] = user_capacity;
  confObj["max_voltage"] = user_max_voltage_cell;
  confObj["cutoff_current"] = user_cutoff_current;

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

  // Skip upload entirely during the CV termination window.
  // At end-of-charge the current taper to <0.3A is the only exit signal.
  // A WiFi TX burst here could artificially suppress the reading and cause
  // the charge cycle to end with the battery only partially full.
  if (cv_phase_critical) {
    Serial.println("[Telemetry] Upload skipped — CV termination phase active (protecting current reading)");
    return;
  }

  HTTPClient http;
  http.begin(SERVER_TELEMETRY_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(3000); // 3 second timeout

  // Raise the guard flag: freeze current readings during WiFi TX burst
  // to prevent rail-droop from shifting the ACS712 zero-point
  wifi_tx_active = true;
  int httpCode = http.POST(json_data);
  wifi_tx_active = false; // TX complete — resume normal current readings

  if (httpCode == 200) {
    String response_payload = http.getString();
    Serial.println("[Telemetry] Raw response: " + response_payload);
    
    // Parse incoming response for pending dashboard config updates
    StaticJsonDocument<512> responseDoc;
    DeserializationError err = deserializeJson(responseDoc, response_payload);
    
    if (!err && responseDoc.containsKey("pending_config")) {
      JsonObject pending = responseDoc["pending_config"];
      Serial.println("[Telemetry] Received new configuration from Dashboard!");
      
      if (pending.containsKey("charge_mode")) {
        user_charging_mode = pending["charge_mode"];
      }
      if (pending.containsKey("discharge_mode")) {
        user_discharge_mode = pending["discharge_mode"];
      }
      if (pending.containsKey("capacity")) {
        user_capacity = pending["capacity"];
        capacity_ah = (config_mode == SERIES) ? user_capacity : (user_capacity * 3.0);
      }
      if (pending.containsKey("max_voltage")) {
        user_max_voltage_cell = pending["max_voltage"];
      }
      if (pending.containsKey("cutoff_current")) {
        user_cutoff_current = pending["cutoff_current"];
      }
      
      // Raise flag to interrupt active loops and pause processes safely
      config_updated = true;
    }

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
