#include "MCP4725.h"
#include "Wire.h"
#include <7semi_ADS1xx5.h>
#include <Preferences.h>
#include "battery_model.h"
#include "bms_wifi_telemetry.h"

#define COMPLETE_DISCHARGE false

ADS1xx5_7semi adc;
Preferences preferences;

MCP4725 MCP(0x61);

#define relay_pin 19
#define I_adc 32
#define PARALLEL 0
#define SERIES 1

#define _switch 23
#define bal1 12
#define bal2 14
#define bal3 27

#define load 13

// Runtime configurable user parameters
int user_charging_mode = SERIES;
int user_discharge_mode = PARALLEL;
float user_capacity = 2.6; // cell capacity
float user_max_voltage_cell = 4.2;
float user_cutoff_current = 0.3; // End-of-charge taper current

// Derived values
#define MAX_VOLTAGE (user_max_voltage_cell * 3.0)
#define MIN_VOLTAGE_CELL 3.0
#define MIN_VOLTAGE 9.2
#define MAX_CURRENT 0.8
#define MAX_CURRENT_PARALLEL (MAX_CURRENT * 3)

#define MIN_SERIES_VOLTAGE 9.6

int dac = 4095;
int dac2 = 255;

bool _display = true;
bool charging = false;
bool pause_balancing = false;

float cell_volt[] = {0, 0, 0};
uint8_t cell_channel[] = {1, 2, 3};
float calibration[] = {0.2077286732379577, 0.20356074801812143, 0.20298407368164226};
float calibration_p[] = {0.20616287921857612, 0.2076627278270508, 0.20707443284903052};
float current_bleed[] = {0, 0, 0};
// float current_comp_p[] = {0.059027, 0.0360655, 0.06818};
float current_compensate = 0; // Runtime-adjustable DC offset for sensor zero-point drift
float last_good_I = 0.0; // Global for cached current to prevent blocking

volatile bool config_updated = false; // Raised when new config is received from Dashboard

// Declared in bms_wifi_telemetry.h — raised during HTTP POST to freeze
// current readings while the WiFi radio droops the ACS712 reference rail
extern bool wifi_tx_active;

// Raised during the CV termination phase where current taper is the only
// signal that decides end-of-charge. WiFi uploads are suspended while this
// is true to prevent TX-induced current spikes from cutting charge prematurely.
bool cv_phase_critical = false;
int charger_channel = 0;
float charger_calibration = 0.20236;
float rate[] = {0, 0, 0};

float voltage_set = 8.9;
float current_set = 1.2;
bool dac_set = false;
bool config_mode = false; // false-paramllel; true-series;
bool lock = false;
bool load_state = false;

float capture[][4] = {{0, 0, 0, 0}, {0, 0, 0, 0}};
float internal_resistance[] = {0, 0, 0};
float raw_cell_volt[] = {0, 0, 0};

// SOC & SOH tracking
float soc = 0.0;
float soh[3] = {100.0, 100.0, 100.0};
float fresh_ir[3] = {0.09, 0.11, 0.13}; // User-provided array of fresh internal resistances
float capacity_ah = 2.6 * 3;           // nominal capacity (updated in setup)
float remaining_capacity_ah = 1.1; // default to 50% start
unsigned long last_time = 0;
float prev_cell_volt[3] = {0, 0, 0};
unsigned long last_balance_time = 0;
bool charging_lock = false;

// ML Health Status
float cycle_count = 0;
float cumulative_discharge_ah = 0;
String health_status[3] = {"UNKNOWN", "UNKNOWN", "UNKNOWN"};
const char* health_labels[] = {"GOOD", "DEGRADING", "DEAD"};

SemaphoreHandle_t i2c_mutex;

void read_cell_voltages() {
  float _cell_volt[] = {0, 0, 0};
  if (xSemaphoreTake(i2c_mutex, portMAX_DELAY) == pdTRUE) {
    for (int i = 0; i < 3; i++) {
      if (!config_mode)
        raw_cell_volt[i] =
            abs((adc.readCH(cell_channel[i]) / calibration_p[i]));
      else {
        _cell_volt[i] =
            abs((adc.readCH(cell_channel[i]) / calibration[i]));
        raw_cell_volt[i] = _cell_volt[i] - ((i != 0) ? _cell_volt[i - 1] : 0);
      }
    }
    xSemaphoreGive(i2c_mutex);
  }

  // Auto calibration based on internal resistance
  float current = last_good_I;
  for (int i = 0; i < 3; i++) {
    if (current > 0.1) {
      cell_volt[i] = raw_cell_volt[i];      // - ((current > 0.1 and user_charging_mode==PARALLEL) ? (abs(current) *
      // current_comp_p[i]) : 0);
    } else if (current < -0.1) {
      cell_volt[i] = raw_cell_volt[i] + abs(current) * internal_resistance[i];
    } else                                        {  
      cell_volt[i] = raw_cell_volt[i];
    }
  }
}

float read_voltage() {
  float v = 0;
  if (xSemaphoreTake(i2c_mutex, portMAX_DELAY) == pdTRUE) {
    v = abs(((adc.readCH(charger_channel)) / charger_calibration));
    xSemaphoreGive(i2c_mutex);
  }
  return v;
}

float read_current() {
  // If WiFi is actively transmitting, the 3.3V rail droops and shifts the
  // ACS712 zero-point. Return the last known-good filtered value immediately
  // to prevent false current spikes from polluting the EMA history.
  
  if (wifi_tx_active) return last_good_I;

  const int num_samples = 60; // 60ms window helps filter 50Hz/60Hz AC noise
  int samples[num_samples];

  for (int i = 0; i < num_samples; i++) {
    samples[i] = analogRead(I_adc);
    delay(1);
  }

  // Insertion sort to find median and remove outliers
  for (int i = 1; i < num_samples; i++) {
    int key = samples[i];
    int j = i - 1;
    while (j >= 0 && samples[j] > key) {
      samples[j + 1] = samples[j];
      j = j - 1;
    }
    samples[j + 1] = key;
  }

  // Average the middle 50% of the sorted samples
  long sum = 0;
  int start_idx = num_samples / 4;
  int end_idx = num_samples - start_idx;
  int valid_samples = end_idx - start_idx;

  for (int i = start_idx; i < end_idx; i++) {
    sum += samples[i];
  }

  float avg_adc = (float)sum / valid_samples;

  // Convert ADC to voltage
  float voltage = (avg_adc * 3.3) / 4095.0;

  // Calculate raw current (ACS712-30A: 66mV/A, 2.48V assumed zero point)
  float raw_I = (voltage - 2.47) / 0.066;

  // Apply Exponential Moving Average (EMA) filter
  static float filtered_I = 0.0;
  static bool first_run = true;

  // Filter transient outlier spikes (e.g. >20A) to prevent noise-induced current overshoots
  if (!first_run && abs(raw_I) > 20.0) {
    raw_I = filtered_I;
  }

  if (first_run) {
    filtered_I = raw_I;
    first_run = false;
  } else {
    // 20% weight to new reading, 80% to historical data
    filtered_I = (0.2 * raw_I) + (0.8 * filtered_I);
  }

  // Deadband: clamp to 0 if noise is extremely low
  if (abs(filtered_I) < 0.05) {
    return 0.0;
  }

  // Topology-aware bleed subtraction:
  // In SERIES mode: the 3 bleed resistors sit in a series string, so the
  // main current sensor sees their average combined effect.
  // In PARALLEL mode: all cells share the same bus — subtracting individual
  // bleed currents would double/triple count the same current.
  float bleed_floor =
      (config_mode == SERIES)
          ? ((current_bleed[0] + current_bleed[1] + current_bleed[2]) / 3.0)
          : 0;

  last_good_I = filtered_I - bleed_floor - current_compensate;
  return last_good_I;
}

float get_true_charge_current() {
  // read_current() already subtracts bleed_floor internally
  return abs(read_current());
}

void relay(bool state) { digitalWrite(relay_pin, !state); }

void DACWrite(uint16_t value) { MCP.setValue(value); }

void cc_mode(float current_set, float max_voltage = -1,
             float (*func)() = read_voltage) {
  if (max_voltage != -1 and (int)(func() * 10) >= (int)(max_voltage * 10)) {
    cv_mode(max_voltage, read_voltage);
    dac_set = true;
    return;
  }

  static float prev_current = -1.0;
  static int prev_dac = -1;
  static float amps_per_step = 0.01; // Initial conservative hardware guess

  float current = read_current();
  float error = current_set - current;

  if (!dac_set) {
    if (abs(error) > 0.03) {
      // 1. Mathematically estimate the hardware's dynamic slope (Amps per DAC
      // step)
      if (prev_dac != -1 && abs(dac - prev_dac) > 5) {
        float d_current = abs(current - prev_current);
        int d_dac = abs(dac - prev_dac);

        // Only update slope if the current actually changed above the sensor's
        // noise floor
        if (d_current > 0.03) {
          float measured_slope = d_current / (float)d_dac;

          // Clamp slope to physical hardware bounds to prevent math blowups
          // (0.001 to 0.1 A/step)
          if (measured_slope < 0.001)
            measured_slope = 0.001;
          if (measured_slope > 0.1)
            measured_slope = 0.1;

          // Apply a low-pass filter (Exponential Moving Average) to learn and
          // smooth the slope
          amps_per_step = (0.7 * amps_per_step) + (0.3 * measured_slope);
        }
      }

      // 2. Mathematically solve for the exact DAC steps needed to close the
      // current error. We apply a damping factor of 0.8 to gently slide into
      // the target without violently overshooting.
      int steps_needed = (int)((abs(error) / amps_per_step) * 0.8);

      // 3. Safety boundaries
      if (steps_needed > 500)
        steps_needed = 500; // Cap maximum jump to prevent catastrophic spikes
      if (steps_needed < 2)
        steps_needed =
            2; // Always ensure we move at least 2 steps so it never stalls

      // Store current state for the next iteration's slope calculation
      prev_dac = dac;
      prev_current = current;

      // 4. Apply the solved adjustment
      if (error >
          0) { // Current too low -> decrease DAC (increases voltage/current)
        dac = (dac - steps_needed < 0) ? 0 : dac - steps_needed;
      } else { // Current too high -> increase DAC (decreases voltage/current)
        dac = (dac + steps_needed > 4095) ? 4095 : dac + steps_needed;
      }
      DACWrite(dac);
    } else {
      dac_set = true;
      prev_dac = -1; // Reset tracker so the next CC cycle starts fresh
    }
  } else {
    // If it drifts by more than 0.1A, reactivate CC loop tracking
    if (abs(error) > 0.01) {
      dac_set = false;
      prev_dac = -1; // Reset tracker
    }
  }
}

void voltage_mode(bool high) {
  digitalWrite(25, !high);
  if (high) {
    DACWrite(4095);
    dac = 4095;
  } else {
    DACWrite(0);
    dac = 0;
  }
}

void cv_mode(float voltage_set, float (*func)()) {
  if (!dac_set) {
    if ((int)(func() * 100) < (int)(voltage_set * 100)) {
      int incr = 100 * (voltage_set - func());
      dac = (dac - incr < 0) ? 0 : dac - incr;
      DACWrite(dac);

    } else if ((int)(func() * 100) > (int)(voltage_set * 100)) {
      int incr = 100 * (func() - voltage_set);
      dac = (dac + incr > 4095) ? 4095 : dac + incr;
      DACWrite(dac);
    } else {
      dac_set = true;
    }
  } else {
    if (abs((int)(func() * 100) - (int)(voltage_set * 100)) > 1) {
      dac_set = false;
    }
  }
}

float b_read_voltage() {
  read_cell_voltages();
  float sum = 0;
  float max = 0;
  for (int i = 0; i < 3; i++) {
    sum += cell_volt[i];
    if (cell_volt[i] > max) max = cell_volt[i];
  }
  // SERIES mode: sum of all 3 cells; PARALLEL mode: average (all same voltage)
  if (config_mode == SERIES)
    return sum;
  else
    return max;
}

void display(int _delay=0) {
  if (_display){
    Serial.print("state: ");
    Serial.print(config_mode ? "SERIES" : "PARALLEL");
    Serial.print(" V_in:");
    Serial.print(read_voltage());
    Serial.print("V V_bat:");
    Serial.print(b_read_voltage());
    Serial.print("V C1:");
    Serial.print(raw_cell_volt[0]);
    Serial.print("V C2:");
    Serial.print(raw_cell_volt[1]);
    Serial.print("V C3:");
    Serial.print(raw_cell_volt[2]);
    Serial.print("V I:");
    Serial.print(read_current());
    Serial.print("A I_bat:");
    Serial.print(get_true_charge_current());
    Serial.print("A SOC:");
    Serial.print(soc);
    Serial.print("% SOH1:");
    Serial.print(soh[0]);
    Serial.print("% H1:");
    Serial.print(health_status[0]);
    Serial.print(" SOH2:");
    Serial.print(soh[1]);
    Serial.print("% H2:");
    Serial.print(health_status[1]);
    Serial.print(" SOH3:");
    Serial.print(soh[2]);
    Serial.print("% H3:");
    Serial.print(health_status[2]);
    Serial.print(" cycles:");
    Serial.print(cycle_count);
    Serial.print(" dac:");
    Serial.print(dac);
    Serial.print(" current bleed[0]: " + String(current_bleed[0]));
    Serial.print(" current bleed[1]: " + String(current_bleed[1]));
    Serial.print(" current bleed[2]: " + String(current_bleed[2]));
    Serial.print(" charging: " + String(charging));
    Serial.println(" load: " + String(load_state));
    if (_delay != 0) delay(_delay);
  }
}

void turn_off_bleeds() {
  if (digitalRead(bal1) == HIGH) {
    digitalWrite(bal1, LOW);
    delay(50);
  }
  if (digitalRead(bal2) == HIGH) {
    digitalWrite(bal2, LOW);
    delay(50);
  }
  if (digitalRead(bal3) == HIGH) {
    digitalWrite(bal3, LOW);
    delay(50);
  }
  current_bleed[0] = 0;
  current_bleed[1] = 0;
  current_bleed[2] = 0;
}

void Balance_code(void *pvParameters) {
  Serial.print("Balance code running on core ");
  Serial.println(xPortGetCoreID());

  for (;;) {
    if (pause_balancing) {
      turn_off_bleeds();
      last_balance_time = 0; // Force re-initialization of dV/dt tracking to
                             // prevent false voltage spikes when unpaused
      vTaskDelay(500 / portTICK_PERIOD_MS);
      continue;
    }

    // Ground-bounce / Crosstalk Mitigation:
    // Temporarily disable active cell balancing (quiet period) to measure
    // clean, unperturbed cell voltages.
    bool b1_was_on = (digitalRead(bal1) == HIGH);
    bool b2_was_on = (digitalRead(bal2) == HIGH);
    bool b3_was_on = (digitalRead(bal3) == HIGH);
    bool any_was_on = (b1_was_on || b2_was_on || b3_was_on);

    if (any_was_on) {
      digitalWrite(bal1, LOW);
      digitalWrite(bal2, LOW);
      digitalWrite(bal3, LOW);
      // Wait for chemistry and ADC input filter to completely settle (100ms)
      vTaskDelay(100 / portTICK_PERIOD_MS);
    }

    // Take clean cell voltage readings with bleed resistors disabled
    read_cell_voltages();

    // Restore previous balancing states immediately to resume bleed action
    // while we perform calculations
    if (any_was_on) {
      digitalWrite(bal1, b1_was_on ? HIGH : LOW);
      digitalWrite(bal2, b2_was_on ? HIGH : LOW);
      digitalWrite(bal3, b3_was_on ? HIGH : LOW);
    }

    float current = read_current();
    unsigned long current_time = millis();

    // Initialization of last_balance_time and prev_cell_volt
    if (last_balance_time == 0) {
      last_balance_time = current_time;
      for (int i = 0; i < 3; i++)
        prev_cell_volt[i] = cell_volt[i];
      vTaskDelay(5000 / portTICK_PERIOD_MS);
      continue;
    }

    float dt = (current_time - last_balance_time) / 1000.0; // seconds
    last_balance_time = current_time;

    // Only start predictive balancing if charging and approaching the top of
    // charge
    if (current > 0.1 &&
        (cell_volt[0] > 4.10 || cell_volt[1] > 4.10 || cell_volt[2] > 4.10)) {
      float time_to_full[3] = {99999, 99999, 99999};
      float max_time = 0;
      float min_volt = 999.0;

      // First pass: find minimum voltage for reactive balancing fallback
      for (int i = 0; i < 3; i++) {
        if (cell_volt[i] < min_volt) {
          min_volt = cell_volt[i];
        }
      }

      for (int i = 0; i < 3; i++) {
        float dV = cell_volt[i] - prev_cell_volt[i];

        // Calculate instantaneous rate (V/s) and apply EMA filter
        float current_rate = dV / dt;

        // Jump-start the EMA filter on first real reading to avoid lag
        if (abs(rate[i]) < 0.00001) {
          rate[i] = current_rate;
        } else {
          rate[i] = (0.2 * current_rate) + (0.8 * rate[i]);
        }

        // Project time to full (user_max_voltage_cell target)
        if (rate[i] > 0.0001) { // Avoid divide by zero
          time_to_full[i] = (user_max_voltage_cell - cell_volt[i]) / rate[i];
        } else if (cell_volt[i] >= user_max_voltage_cell) {
          time_to_full[i] = 0; // Cell is already full
        }

        // Track the slowest charging cell
        if (time_to_full[i] > max_time && time_to_full[i] != 99999) {
          max_time = time_to_full[i];
        }

        prev_cell_volt[i] = cell_volt[i];
      }

      // Trigger bleed resistors using a hybrid approach:
      // 1. Predictive: Finishing >= 60 seconds faster than the slowest cell
      // 2. Reactive Fallback: Voltage is >= 30mV higher than the lowest cell
      // (helps near CV phase)
      // (helps near CV phase)
      if (user_charging_mode == SERIES) {
        int state_bal1 = ((time_to_full[0] < max_time - 20 ||
                           (cell_volt[0] - min_volt) >= 0.05) &&
                          cell_volt[0] > (user_max_voltage_cell - 0.05))
                             ? HIGH
                             : LOW;
        int state_bal2 = ((time_to_full[1] < max_time - 20 ||
                           (cell_volt[1] - min_volt) >= 0.05) &&
                          cell_volt[1] > (user_max_voltage_cell - 0.05))
                             ? HIGH
                             : LOW;
        int state_bal3 = ((time_to_full[2] < max_time - 20 ||
                           (cell_volt[2] - min_volt) >= 0.05) &&
                          cell_volt[2] > (user_max_voltage_cell - 0.05))
                             ? HIGH
                             : LOW;

        if (digitalRead(bal1) != state_bal1) {
          digitalWrite(bal1, state_bal1);
          delay(50);
        }
        current_bleed[0] = (state_bal1 == HIGH) ? (cell_volt[0] / 10.0) : 0;

        if (digitalRead(bal2) != state_bal2) {
          digitalWrite(bal2, state_bal2);
          delay(50);
        }
        current_bleed[1] = (state_bal2 == HIGH) ? (cell_volt[1] / 10.0) : 0;

        if (digitalRead(bal3) != state_bal3) {
          digitalWrite(bal3, state_bal3);
          delay(50);
        }
        current_bleed[2] = (state_bal3 == HIGH) ? (cell_volt[2] / 10.0) : 0;
      } else {
        turn_off_bleeds();
      }

    } else {
      // Safe state
      turn_off_bleeds();
      for (int i = 0; i < 3; i++)
        prev_cell_volt[i] = cell_volt[i];
    }

    // Evaluate every 5 seconds to get a clean dV/dt reading
    vTaskDelay(5000 / portTICK_PERIOD_MS);
  }
}

void set_mode(bool state) {
  if (config_mode != state || capacity_ah == 0) {
    config_mode = state;
    float old_capacity = capacity_ah;
    capacity_ah = (state == SERIES) ? user_capacity : (user_capacity * 3.0);

    if (old_capacity > 0 && old_capacity != capacity_ah) {
      // Scale absolute Amp-hours when switching topology so SOC% and Cycle%
      // remain perfectly constant
      float scale_factor = capacity_ah / old_capacity;
      remaining_capacity_ah *= scale_factor;
      cumulative_discharge_ah *= scale_factor;
    }
  }
  digitalWrite(_switch, !state);
}

void switch_load(bool state, int mode = -1) {
  if (mode == -1) mode = user_discharge_mode;
  if (state) {
    turn_off_bleeds();

    set_mode(mode);
    Serial.println("Load ON - DISCHARGE mode");
  } else {
    set_mode(mode);
    Serial.println("Load OFF");
  }
  digitalWrite(load, state);
  load_state = state;
}

bool check_cutoff() {
  read_cell_voltages();
  for (int i = 0; i < 3; i++) {
    if (cell_volt[i] <= MIN_VOLTAGE_CELL) {
      return true;
    }
  }
  return false;
}

void monitor() {
  float signed_current = read_current();
  float current = abs(signed_current);

  if (abs(capture[0][3] - signed_current) >= 0.5) { // Increased threshold to 0.5A for better Signal-to-Noise
    read_cell_voltages();
    for (int i = 0; i < 3; i++)
      capture[1][i] = raw_cell_volt[i];
    capture[1][3] = signed_current;

    for (int i = 0; i < 3; i++) {
      float new_ir = abs((capture[0][i] - capture[1][i]) /
                         (capture[1][3] - capture[0][3]));
      if (new_ir > 0.0 && new_ir < 1.0) {
        // Apply EMA filter to smooth out calculation variations
        float smoothed_ir = (0.1 * new_ir) + (0.9 * internal_resistance[i]);
        
        // Only write to flash if value changed significantly to prevent wear
        if (abs(internal_resistance[i] - smoothed_ir) > 0.002) {
          internal_resistance[i] = smoothed_ir;
          String key = "ir" + String(i);
          preferences.putFloat(key.c_str(), smoothed_ir);
        }
      }
      // Serial.println();
      // Serial.print("Internal resistance: ");
      // Serial.print(internal_resistance[i]);
      // Serial.println();
    }
    for (int i = 0; i < 3; i++)
      capture[0][i] = raw_cell_volt[i];
    capture[0][3] = signed_current;
  } else {
    read_cell_voltages();
    for (int i = 0; i < 3; i++)
      capture[0][i] = raw_cell_volt[i];
    capture[0][3] = signed_current;
  }

  // SOC and cycle calculation — dt_hours computed ONCE before last_time update
  unsigned long current_time = millis();
  float dt_hours = (last_time != 0) ? ((current_time - last_time) / 3600000.0) : 0.0;

  if (last_time != 0) {
    remaining_capacity_ah += signed_current * dt_hours; // Integrate current

    if (remaining_capacity_ah > capacity_ah)
      remaining_capacity_ah = capacity_ah;
    if (remaining_capacity_ah < 0)
      remaining_capacity_ah = 0;

    soc = (remaining_capacity_ah / capacity_ah) * 100.0;
    
    // Save SOC to flash if it has changed by more than 1% to prevent memory wear
    static float last_saved_soc = -1.0;
    if (last_saved_soc == -1.0) last_saved_soc = soc; // Initialize
    
    if (abs(soc - last_saved_soc) >= 1.0) {
        preferences.putFloat("soc", soc);
        last_saved_soc = soc;
    }

    // Cycle counting: accumulate discharged Ah before last_time is overwritten
    if (signed_current < -0.1 && dt_hours > 0) {
      cumulative_discharge_ah += abs(signed_current) * dt_hours;
      if (cumulative_discharge_ah >= capacity_ah) {
        cycle_count += 1.0;
        cumulative_discharge_ah -= capacity_ah;
        preferences.putFloat("cycles", cycle_count);
      }
    }
  }
  last_time = current_time;

  //   calculation based on internal resistance growth for each cell
  for (int i = 0; i < 3; i++) {
    soh[i] = 100.0 - ((internal_resistance[i] - fresh_ir[i]) / (0.15 - fresh_ir[i])) * 100.0;
    if (soh[i] > 100)
      soh[i] = 100.0;
    if (soh[i] < 0)
      soh[i] = 0.0;

    // ML Health Prediction for each cell
    float features[10];
    features[0] = raw_cell_volt[i];
    features[1] = abs(signed_current);
    features[2] = 25.0; // Placeholder for Temperature (C)
    features[3] = internal_resistance[i] * 1000.0; // Convert to mOhm
    features[4] = soc;
    features[5] = cycle_count;
    features[6] = capacity_ah * 1000.0; // Convert to mAh
    features[7] = (4.2 - features[0]) / (cycle_count + 1.0); // Voltage Drop Rate
    features[8] = features[3] / (cycle_count + 1.0);         // Resistance Trend
    features[9] = features[0] * features[1];                 // Power (W)

    int health_index = predict_health(features);
    if (health_index >= 0 && health_index <= 2) {
      health_status[i] = health_labels[health_index];
    }
  }
}

void Monitor_Task(void *pvParameters) {
  Serial.print("Monitor code running on core ");
  Serial.println(xPortGetCoreID());
  for (;;) {
    monitor();
    vTaskDelay(500 / portTICK_PERIOD_MS);
  }
}

void Telemetry_Task(void *pvParameters) {
  Serial.print("Telemetry code running on core ");
  Serial.println(xPortGetCoreID());
  for (;;) {
    update_wifi_telemetry();
    vTaskDelay(500 / portTICK_PERIOD_MS);
  }
}

void setup() {
  i2c_mutex = xSemaphoreCreateMutex();

  preferences.begin("bms", false);
  internal_resistance[0] = preferences.getFloat("ir0", 0.04);
  internal_resistance[1] = preferences.getFloat("ir1", 0.04);
  internal_resistance[2] = preferences.getFloat("ir2", 0.04);
  
  // Load Config
  user_charging_mode = preferences.getInt("chg_mode", SERIES);
  user_discharge_mode = preferences.getInt("dis_mode", PARALLEL);
  user_capacity = preferences.getFloat("cap_ah", 2.6);
  user_max_voltage_cell = preferences.getFloat("max_v", 4.2);
  user_cutoff_current = preferences.getFloat("cut_i", 0.3);

  // Initialize capacity_ah based on loaded user capacity and current config mode
  capacity_ah = (config_mode == SERIES) ? user_capacity : (user_capacity * 3.0);

  // Load SOC and initialize remaining capacity
  soc = preferences.getFloat("soc", 50.0); // Default to 50% if never saved
  cycle_count = preferences.getFloat("cycles", 0.0);
  remaining_capacity_ah = (soc / 100.0) * capacity_ah;

  pinMode(_switch, OUTPUT);
  pinMode(bal1, OUTPUT);
  pinMode(bal2, OUTPUT);
  pinMode(bal3, OUTPUT);
  pinMode(load, OUTPUT);
  digitalWrite(load, LOW);
  digitalWrite(bal1, LOW);
  digitalWrite(bal2, LOW);
  digitalWrite(bal3, LOW);
  digitalWrite(_switch, HIGH);

  // Start with a safe value (1.25V at DAC usually results in lower Vout)
  Wire.begin();

  MCP.begin();
  // calibrate max voltage
  MCP.setMaxVoltage(5);

  Serial.begin(115200);
  if (!adc.begin()) {
    Serial.println("Failed to connect to ADS1xx5!");
    while (1)
      ;
  }
  Serial.println("ADS1xx5 Connected");

  // Optional: Set PGA (reference voltage)
  // Default: ±2.048V
  // To change: use
  // PGA_6_144V  6.144V
  // PGA_4_096V  4.096V
  // PGA_1_024V  1.024V
  // PGA_0_512V  0.512V
  // PGA_0_256V  0.256V
  adc.setRefV(PGA_4_096V);

  Serial.print("\nVoltage:\t");
  pinMode(relay_pin, OUTPUT);
  digitalWrite(relay_pin, HIGH);
  pinMode(25, OUTPUT);
  Serial.println();
  DACWrite(4095);
  Serial.println(MCP.getVoltage());
  DACWrite(4095);
  switch_load(false);
  delay(5000);

  // Auto-calibrate the current sensor zero-point offset at startup.
  // The relay is OFF and load is OFF so no real current should be flowing.
  // Any non-zero reading is pure sensor drift — capture and cancel it.
  float _current_compensate = 0;
  current_compensate = 0;
  for (int i = 0; i < 10; i++)
    read_current(); // Warm up the EMA filter first
  for (int i = 0; i < 10; i++)
    _current_compensate += read_current();
  current_compensate = _current_compensate / 10.0;
  Serial.println("[BMS] Current sensor offset calibrated: " + String(current_compensate) + " A");

  // Initialize WiFi and HTTP Telemetry Client
  init_wifi_telemetry();

  xTaskCreatePinnedToCore(Balance_code, "BalanceTask", 10000, NULL, 1, NULL, 0);

  xTaskCreatePinnedToCore(Monitor_Task, "MonitorTask", 10000, NULL, 1, NULL, 0);

  xTaskCreatePinnedToCore(Telemetry_Task, "TelemetryTask", 10000, NULL, 1, NULL, 0);
}

/*
TODO: implement data collecition
*/

bool check_config_abort() {
  if (config_updated) {
    Serial.println("[BMS] Configuration update detected! Aborting active charge/discharge process...");
    relay(false);           // Turn off charger relay
    switch_load(false);     // Turn off load
    DACWrite(4095);         // Minimum charger output
    dac = 4095;
    charging = false;
    lock = false;
    charging_lock = false;
    return true;
  }
  return false;
}

void recovery_charge_override(){
  Serial.println("recovery");
  Serial.println(config_mode);
  if ((config_mode == SERIES && b_read_voltage() < MIN_SERIES_VOLTAGE) || (config_mode == PARALLEL && b_read_voltage() < MIN_VOLTAGE_CELL)){
    set_mode(PARALLEL);
    voltage_mode(LOW);

    unsigned long cv_pre_start = millis();
    while (abs(read_voltage() - b_read_voltage()) > 0.15) {
      if (millis() - cv_pre_start > 30000) break; // 30s timeout
      if (check_config_abort()) return;
      Serial.println("--------------recovery cv mode---------------");
      cv_mode(b_read_voltage(), read_voltage);
      display();
      if (dac == 4095) break;
    }
    relay(true);
    for (int i = 0; i < 100; i++) {
      if (config_updated) return;
      while ((int)(b_read_voltage() * 10) != (int)(((MIN_SERIES_VOLTAGE * 10) / 3) + 0.2)) {
        if (check_config_abort()) return;
        Serial.println("--------------recovery cc mode---------------");
        cc_mode(MAX_CURRENT_PARALLEL);
        display();
      }
    }

    while (read_current() > user_cutoff_current) {
      if (check_config_abort()) return;
      Serial.println("--------------recovery cv mode---------------");
      cv_mode((MIN_SERIES_VOLTAGE/3) + 0.2, b_read_voltage);    
      display();
    }

    relay(false);
  }
}

void calibrate_current(){
  cv_phase_critical = true;
  delay(100);
  current_compensate = 0;
  float _current_compensate = 0;
  for (int i = 0; i < 20; i++){
    read_current(); // Warm up the EMA filter first
  }
  for (int i = 0; i < 20; i++){
    _current_compensate += read_current();
  }
  current_compensate = _current_compensate / 20.0;
  Serial.println("[BMS] Current sensor offset calibrated: " + String(current_compensate) + " A");
  cv_phase_critical = false;
  delay(100);
}

void loop() {
  if (config_updated) {
    Serial.println("[BMS] Configuration update detected! Pausing operations for 2 seconds to apply settings...");
    Serial.printf("[BMS] Loaded new values -> ChgMode: %d | DisMode: %d | Cap: %.2f Ah | MaxV: %.2f V | CutI: %.2f A\n",
                  user_charging_mode, user_discharge_mode, user_capacity, user_max_voltage_cell, user_cutoff_current);
    relay(false);
    switch_load(false);
    DACWrite(4095);
    dac = 4095;
    charging = false;
    lock = false;
    charging_lock = false;
    
    // Commit new configuration parameters to Preferences safely on the main thread (Core 1)
    preferences.putInt("chg_mode", user_charging_mode);
    preferences.putInt("dis_mode", user_discharge_mode);
    preferences.putFloat("cap_ah", user_capacity);
    preferences.putFloat("max_v", user_max_voltage_cell);
    preferences.putFloat("cut_i", user_cutoff_current);

    delay(2000);
    config_updated = false;
    Serial.println("[BMS] Resuming operations with new configuration parameters.");
    return;
  }

  display();

  if ((read_voltage() < 4.2 and charging_lock) || (COMPLETE_DISCHARGE == true and check_cutoff() and lock)){
    charging_lock = false;
  } 

  if (read_voltage() > 4.2 and ((int)(b_read_voltage()) < (int)((config_mode == SERIES) ? MAX_VOLTAGE : user_max_voltage_cell)) and !charging_lock) {
    lock = false;
    charging = true;
    switch_load(false);

    recovery_charge_override();
    if (config_updated) return;
    
    float max_voltage = MAX_VOLTAGE;
    float max_current = MAX_CURRENT;
    if (user_charging_mode == SERIES){
      voltage_mode(HIGH);
      set_mode(SERIES);
    }
    else{
      voltage_mode(LOW);
      set_mode(PARALLEL);
      max_voltage = user_max_voltage_cell;
      max_current = MAX_CURRENT_PARALLEL;
    }

    calibrate_current();

    unsigned long cv_pre_start = millis();
    while (abs(read_voltage() - b_read_voltage()) > 0.15) {
      if (millis() - cv_pre_start > 30000) break; // 30s timeout
      if (check_config_abort()) break;
      Serial.println("--------------cv mode---------------");
      cv_mode(b_read_voltage(), read_voltage);
      display();

      if (dac == 4095 and b_read_voltage() < read_voltage()){
        recovery_charge_override();
      } 
    }
    if (config_updated) return;

    relay(true);
    for (int i = 0; i < 100; i++) {
      if (config_updated) break;
      while (b_read_voltage() < max_voltage) {
        if (check_config_abort()) break;
        Serial.println("--------------cc mode---------------");
        cc_mode(max_current);
        display();
      }
    }
    if (config_updated) return;

    // ── CV Termination Phase ─────────────────────────────────────────────
    // This is the most current-sensitive window of the entire charge cycle.
    // The only exit condition is current tapering below the user cutoff current.
    // WiFi uploads are suspended here to guarantee the TX burst cannot induce
    // a false current dip that would terminate the charge cycle prematurely.
    cv_phase_critical = true;
    unsigned long cutoff_timer = 0;
    bool checking_cutoff = false;
    unsigned long check_start_time = 0;
    unsigned long last_check_time = 0;

    while (true) {
      if (check_config_abort()) break;

      float current = abs(read_current());
      float cutoff = user_cutoff_current;

      cv_mode(max_voltage, b_read_voltage);
      display();

      if (!checking_cutoff) {
        if (current <= cutoff && (millis() - last_check_time > 20000 || last_check_time == 0)) {
          checking_cutoff = true;
          pause_balancing = true;
          turn_off_bleeds();
          check_start_time = millis();
          cutoff_timer = 0;
        }
      } else {
        if (millis() - check_start_time > 1000) {
          if (current <= cutoff + 0.02) {
            if (cutoff_timer == 0) {
              cutoff_timer = millis();
            } else if (millis() - cutoff_timer > 3000) {
              pause_balancing = false;
              break;
            }
          } else {
            checking_cutoff = false;
            pause_balancing = false;
            cutoff_timer = 0;
            last_check_time = millis();
          }
        }
      }
    }
    cv_phase_critical = false;
    if (config_updated) return;
    // ────────────────────────────────────────────────────────────────────
    
    // Charge cycle completed perfectly, sync SOC to 100% to eliminate drift
    soc = 100.0;
    remaining_capacity_ah = capacity_ah;
    preferences.putFloat("soc", soc);

    relay(false);
    Serial.println("--------------end---------------");
    charging_lock = true;
    lock = false;
    set_mode(PARALLEL);
    charging = false;

    calibrate_current();
  } 
  
  else if ((b_read_voltage() <= ((config_mode == SERIES)? MIN_VOLTAGE:MIN_VOLTAGE_CELL)) || check_cutoff()) {
    if ((COMPLETE_DISCHARGE == true) && (config_mode == SERIES) && !lock){
      // Serial.println("entered");
      switch_load(false);
      relay(false);
      // delay(1000);
      switch_load(true, PARALLEL);
    }
    else{
      relay(false);
      switch_load(false);
      // Serial.println("lock initiated");
      lock = true;
    }
  } 
 
  if (!lock and !load_state) {
    delay(100);
    if (COMPLETE_DISCHARGE == true) switch_load(true, SERIES);
    else switch_load(true);
  } 
  else if (lock and load_state){
    switch_load(false);
    relay(false);
  }
}
