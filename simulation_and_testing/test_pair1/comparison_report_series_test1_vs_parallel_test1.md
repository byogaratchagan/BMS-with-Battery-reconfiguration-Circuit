# BMS Configuration Comparison Report

**series_test1** vs **parallel_test1**

## 1. Raw Telemetry Energy & Time

| Metric | series_test1 | parallel_test1 | Difference |
|---|---|---|---|
| Charge Energy (Logged DC Wh) | 13.215 | 11.022 | 2.193 Wh |
| Charge Time | 02:18:53 (8333s) | 02:24:53 (8693s) | 00:06:00 (360s) |
| Discharge Energy (Wh) | 6.289 | 6.425 | 0.137 Wh |
| Discharge Time | 01:04:43 (3883s) | 01:07:26 (4046s) | 00:02:43 (163s) |

### Capacity Delivered

**parallel_test1** delivered **0.137 MORE Wh** during discharge than **series_test1**. (2.17% improvement)

## DC Charger Meter Analysis

### Normalized Energy Savings (Normalized to 6.425 Wh delivered capacity)

- To deliver 6.425 Wh, **series_test1** requires: **11.852 Wh** (DC Charger Meter)
- To deliver 6.425 Wh, **parallel_test1** requires: **12.700 Wh** (DC Charger Meter)

**🏆 CONCLUSION:** **series_test1** saves **0.848 Wh (6.68%)** compared to **parallel_test1**.

### Overall System Efficiency

- **series_test1** Efficiency: **54.21%**
- **parallel_test1** Efficiency: **50.59%**

**🏆 WINNER:** **series_test1** is **3.62%** MORE efficient than **parallel_test1**! (7.16% relative improvement)

## AC Wall Meter Analysis

### Normalized Energy Savings (Normalized to 6.425 Wh delivered capacity)

- To deliver 6.425 Wh, **series_test1** requires: **35.760 Wh** (AC Wall Meter)
- To deliver 6.425 Wh, **parallel_test1** requires: **41.000 Wh** (AC Wall Meter)

**🏆 CONCLUSION:** **series_test1** saves **5.240 Wh (12.78%)** compared to **parallel_test1**.

### Overall System Efficiency

- **series_test1** Efficiency: **17.97%**
- **parallel_test1** Efficiency: **15.67%**

**🏆 WINNER:** **series_test1** is **2.30%** MORE efficient than **parallel_test1**! (14.65% relative improvement)

