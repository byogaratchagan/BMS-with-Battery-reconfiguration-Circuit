# BMS-with-Battery-Reconfiguration-Circuit

Reconfigurable Battery Management System (BMS) that dynamically switches a three-cell Li-ion battery pack between Series and Parallel configurations using an ESP32-controlled MOSFET switching network.

In series mode, the three cells are connected end-to-end, producing an output voltage approximately three times that of an individual cell (approximately 9-12.6 V for Li-ion cells).

In parallel mode, the cells share common positive and negative terminals, maintaining the voltage of a single cell (approximately 3-4.2 V).

It also includes **ML based cell health prediction** trained based on NASA Battery dataset.

Along with health prediction, measurements like SOC, SOH, Internal resistance are also calculated.

Also supported with **Early balancing** so that the charging process takes less time than intended.

Test Run Results
| Metric | Series | Parallel | Better configuration |
| :--- | :---: | :---: | :--- |
| Charge time | 02:10:02 | 02:28:54 | Series faster |
| Discharge time | 01:03:25 | 01:06:20 | Series faster |
| DC-side Wh (normalized to 6.444 Wh) | 11.200 | 13.220 | Series saves 15.28% |
| DC-side efficiency | 57.54% | 48.75% | Series (+18.03% rel.) |
| AC-side Wh (normalized) | 35.000 | 41.967 | Series saves 16.60% |
| AC-side efficiency | 18.41% | 15.36% | Series (+19.91% rel.) |
