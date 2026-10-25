
/*
 * Generated Battery Health Model
 * Features order:
 * 0: Voltage (V)
 * 1: Current (A)
 * 2: Temperature (C)
 * 3: Internal Resistance (mOhm)
 * 4: SOC (%)
 * 5: Cycle Count
 * 6: Capacity (mAh)
 * 7: Voltage Drop Rate
 * 8: Resistance Trend
 * 9: Power (W)
 */

int predict_health(float* features) {
  if (features[3] <= 23.550258f) {
    if (features[5] <= 452.236313f) {
      return 0;
    } else {
      if (features[6] <= 1371.002625f) {
        return 2;
      } else {
        return 1;
      }
    }
  } else {
    if (features[6] <= 1434.118103f) {
      if (features[1] <= 2.512889f) {
        if (features[3] <= 46.632183f) {
          if (features[0] <= 3.535234f) {
            return 2;
          } else {
            return 1;
          }
        } else {
          if (features[9] <= 8.286810f) {
            return 2;
          } else {
            return 2;
          }
        }
      } else {
        return 1;
      }
    } else {
      if (features[3] <= 68.882885f) {
        if (features[5] <= 214.866943f) {
          if (features[3] <= 31.825687f) {
            return 0;
          } else {
            return 1;
          }
        } else {
          if (features[5] <= 1637.495911f) {
            return 1;
          } else {
            return 2;
          }
        }
      } else {
        if (features[6] <= 1915.525574f) {
          return 2;
        } else {
          return 1;
        }
      }
    }
  }
}
