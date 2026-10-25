import re
import sys

with open('bms/bms.ino', 'r') as f:
    code = f.read()

# Fix 4: MAX_VOLTAGE
code = code.replace('#define MAX_VOLTAGE (user_max_voltage_cell * 3.0)', 'inline float MAX_VOLTAGE() { return user_max_voltage_cell * 3.0f; }')

# Fix 10: last_good_I global
code = code.replace('float current_compensate = 0; // Runtime-adjustable DC offset for sensor zero-point drift',
                    'float current_compensate = 0; // Runtime-adjustable DC offset for sensor zero-point drift\nfloat last_good_I = 0.0; // Global for cached current to prevent blocking')
code = code.replace('static float last_good_I = 0.0;', '')

# Fix 10: read_cell_voltages using last_good_I
code = code.replace('float current = read_current();', 'float current = last_good_I;')

# Fix 5: get_true_charge_current
old_get_true = '''float get_true_charge_current() {
  float total_current = read_current();
  float bleed_current = 0;

  // Calculate exact bleed current drawn by 10 ohm resistors
  if (digitalRead(bal1) == HIGH)
    bleed_current += cell_volt[0] / 10.0;
  if (digitalRead(bal2) == HIGH)
    bleed_current += cell_volt[1] / 10.0;
  if (digitalRead(bal3) == HIGH)
    bleed_current += cell_volt[2] / 10.0;

  float true_current = total_current - bleed_current;
  if (true_current < 0)
    true_current = 0;

  return abs(true_current);
}'''
new_get_true = '''float get_true_charge_current() {
  // read_current() already subtracts bleed_floor internally
  return abs(read_current());
}'''
code = code.replace(old_get_true, new_get_true)

# Fix 6: Recovery CV hardcoded 0.3A
code = code.replace('while (read_current() > 0.3) {', 'while (read_current() > user_cutoff_current) {')

# Fix 9: calibrate_current
code = code.replace('for (int i = 0; i < 100; i++){\n    Serial.println(read_current()); // Warm up the EMA filter first\n  }', 'for (int i = 0; i < 20; i++){\n    read_current(); // Warm up the EMA filter first\n  }')
code = code.replace('for (int i = 0; i < 100; i++){\n    _current_compensate += read_current();\n    Serial.println(_current_compensate); // Warm up the EMA filter first\n  }', 'for (int i = 0; i < 20; i++){\n    _current_compensate += read_current();\n  }')
code = code.replace('current_compensate = _current_compensate / 100.0;', 'current_compensate = _current_compensate / 20.0;')

# Fix 8: CV pre-equalization
code = code.replace('while ((int)(read_voltage() * 10) != (int)(b_read_voltage() * 10)) {', 'unsigned long cv_pre_start = millis();\n    while (abs(read_voltage() - b_read_voltage()) > 0.15) {\n      if (millis() - cv_pre_start > 30000) break; // 30s timeout')

# Fix 2: CC loop != float comparison
code = code.replace('while ((int)(b_read_voltage() * 10) != (int)(max_voltage * 10)) {', 'while (b_read_voltage() < max_voltage) {')

# Fix 1 & 2 & 3: CV termination gated logic
old_cv_term = '''    cv_phase_critical = true;
    while (abs(read_current()) > user_cutoff_current) {
      if (check_config_abort()) break;
      Serial.println("--------------cv mode---------------");
      cv_mode(max_voltage, b_read_voltage);
      display();
    }
    cv_phase_critical = false;'''
new_cv_term = '''    cv_phase_critical = true;
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
    cv_phase_critical = false;'''

code = code.replace(old_cv_term, new_cv_term)

with open('bms/bms.ino', 'w') as f:
    f.write(code)

print('Success')
