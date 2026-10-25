/*
 * Edge-AI Battery Health Model (NASA Aging + Fault Tolerant)
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
  if (features[6] <= 2100.183105f) {
    if (features[6] <= 1499.981262f) {
      return 2;
    } else {
      if (features[0] <= 2.969174f) {
        if (features[4] <= 1.340580f) {
          return 2;
        } else {
          return 2;
        }
      } else {
        if (features[3] <= 187.535290f) {
          if (features[0] <= 3.154864f) {
            if (features[4] <= 38.279738f) {
              return 1;
            } else {
              return 2;
            }
          } else {
            if (features[0] <= 3.199433f) {
              if (features[4] <= 42.936584f) {
                return 1;
              } else {
                return 2;
              }
            } else {
              return 1;
            }
          }
        } else {
          return 2;
        }
      }
    }
  } else {
    if (features[0] <= 2.980103f) {
      if (features[4] <= 0.553348f) {
        return 0;
      } else {
        if (features[4] <= 1.134845f) {
          return 2;
        } else {
          return 2;
        }
      }
    } else {
      if (features[3] <= 175.007526f) {
        if (features[0] <= 3.198040f) {
          if (features[4] <= 39.562783f) {
            return 0;
          } else {
            return 2;
          }
        } else {
          return 0;
        }
      } else {
        return 2;
      }
    }
  }
}
