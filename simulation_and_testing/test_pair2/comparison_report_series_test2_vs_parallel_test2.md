# BMS Configuration Comparison Report

**series_test2** vs **parallel_test2**

## 1. Raw Telemetry Energy & Time

| Metric | series_test2 | parallel_test2 | Difference |
|---|---|---|---|
| Charge Energy (Logged DC Wh) | 12.425 | 11.377 | 1.047 Wh |
| Charge Time | 02:10:02 (7802s) | 02:28:54 (8934s) | 00:18:52 (1132s) |
| Discharge Energy (Wh) | 6.444 | 6.142 | 0.302 Wh |
| Discharge Time | 01:03:25 (3805s) | 01:06:20 (3980s) | 00:02:55 (175s) |

### Capacity Delivered

**series_test2** delivered **0.302 MORE Wh** during discharge than **parallel_test2**. (4.92% improvement)

## DC Charger Meter Analysis

### Normalized Energy Savings (Normalized to 6.444 Wh delivered capacity)

- To deliver 6.444 Wh, **series_test2** requires: **11.200 Wh** (DC Charger Meter)
- To deliver 6.444 Wh, **parallel_test2** requires: **13.220 Wh** (DC Charger Meter)

**🏆 CONCLUSION:** **series_test2** saves **2.020 Wh (15.28%)** compared to **parallel_test2**.

### Overall System Efficiency

- **series_test2** Efficiency: **57.54%**
- **parallel_test2** Efficiency: **48.75%**

**🏆 WINNER:** **series_test2** is **8.79%** MORE efficient than **parallel_test2**! (18.03% relative improvement)

## AC Wall Meter Analysis

### Normalized Energy Savings (Normalized to 6.444 Wh delivered capacity)

- To deliver 6.444 Wh, **series_test2** requires: **35.000 Wh** (AC Wall Meter)
- To deliver 6.444 Wh, **parallel_test2** requires: **41.967 Wh** (AC Wall Meter)

**🏆 CONCLUSION:** **series_test2** saves **6.967 Wh (16.60%)** compared to **parallel_test2**.

### Overall System Efficiency

- **series_test2** Efficiency: **18.41%**
- **parallel_test2** Efficiency: **15.36%**

**🏆 WINNER:** **series_test2** is **3.06%** MORE efficient than **parallel_test2**! (19.91% relative improvement)

