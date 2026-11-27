"""
As-Routed ngspice-46 Corner Verification Suite for planar_transformer_ee22_2l (Rev 1.0, 1:1, 12T : 12T)
Core: EE22/08/13 (PC95 Mn-Zn ferrite, Ae=72.7 mm^2, le=40.6 mm, Ve=2950 mm^3, AL=5000 +-25% nH/T^2)
Uses exact routed copper lengths from verify_windings.py:
  - Single 2-layer 0.80mm board (12T CW, 420um x 35um 1oz Cu): 773.83 mm (MLT_eff = 64.49 mm)
  - Stacked 1:1 pair (Board 1 PRI + 0.10mm Kapton + Flipped Board 2 SEC):
      * R_pri = R_sec = 0.925 ohm @ 25C / 1.050 ohm @ 60C (Dowell F_R @ 200kHz, p=2 -> ~1.008 -> 1.058 ohm)
      * 1D MMF L_lk (0.80mm FR-4 + 0.10mm Kapton) = 1.67 uH, C_ww = 52.8 pF
Models friend's mosfet_gate_driver (a00c78f) full-bridge rectifier + 4.7uF cap + BC547/BC557 totem-pole load.
"""
import ctypes
import math
import os
import re

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
NGSPICE_DLL = r"R:\appsfore\bin\ngspice.dll"

ng = ctypes.CDLL(NGSPICE_DLL)
CB_SENDCHAR = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
CB_SENDSTAT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
CB_EXIT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
log_lines = []

@CB_SENDCHAR
def cb_char(msg, ident, userdata):
    if msg:
        log_lines.append(msg.decode("utf-8", errors="replace"))
    return 0
@CB_SENDSTAT
def cb_stat(msg, ident, userdata): return 0
@CB_EXIT
def cb_exit(status, imm, qexit, ident, userdata): return status

ng.ngSpice_Init.argtypes = [CB_SENDCHAR, CB_SENDSTAT, CB_EXIT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
ng.ngSpice_Init.restype = ctypes.c_int
ng.ngSpice_Command.argtypes = [ctypes.c_char_p]
ng.ngSpice_Command.restype = ctypes.c_int
ng.ngSpice_Init(cb_char, cb_stat, cb_exit, None, None, None, None)

# Exact Rev 1.0 as-routed parameters (60 C, 1 oz Cu, 2x 0.80 mm 2L FR-4 + 0.10 mm Kapton)
NP, NS = 12, 12
AE = 72.7e-6
VE = 2.95e-6
R_DC_60 = 1.050
MLT_EFF = 0.06449
B_CU = 0.00362
H_FR4 = 0.00073  # dielectric thickness inside 0.80mm board
H_KAP = 0.00010  # 0.10mm Kapton sheet
H_CU = 35e-6
MU0 = 4e-7 * math.pi
EPS0 = 8.8541878e-12
RHO_60 = 1.724e-8 * (1 + 0.00393 * 40)

# 1D MMF L_lk for 2-board P-P | Kapton | S-S stack
L_LK = MU0 * (MLT_EFF / B_CU) * (NP ** 2) * (H_KAP + 2 * (0.25 * H_FR4) + 2 * (H_CU / 3.0))
# Inter-winding capacitance across 0.10mm Kapton (er=3.4) + 2x 15um soldermask (er=3.8) -> eff gap ~0.13mm
C_WW = EPS0 * 3.5 * (B_CU * MLT_EFF) / 0.00013 * 0.70 * 1.10

def dowell_Fr(f_hz, p=2.0):
    eta = (6 * 0.42e-3) / B_CU
    delta = math.sqrt(RHO_60 / (math.pi * f_hz * MU0))
    Delta = (H_CU / delta) * math.sqrt(eta)
    M = Delta * (math.sinh(2*Delta) + math.sin(2*Delta)) / (math.cosh(2*Delta) - math.cos(2*Delta))
    D = 2*Delta * (math.sinh(Delta) - math.sin(Delta)) / (math.cosh(Delta) + math.cos(Delta))
    return M + ((p*p - 1.0) / 3.0) * D

def pc95_core_loss_w(f_hz, bpk_t):
    pcv = 350e3 * ((f_hz / 100e3) ** 1.65) * ((bpk_t / 0.200) ** 2.65)
    return pcv * VE

def run_case(name, vin, fsw, iload, al_nh, diode_mode="SCHOTTKY"):
    lm = al_nh * 1e-9 * (NP ** 2)
    fr = dowell_Fr(fsw, p=2.0)
    r_ac = R_DC_60 * fr
    T = 1.0 / fsw
    t_dead = 80e-9
    t_edge = 25e-9
    t_on = T / 2.0 - t_dead - t_edge
    bpk_t = vin * (T / 2.0 - t_dead) / (2.0 * NP * AE)
    bpk_mt = bpk_t * 1e3
    p_core = pc95_core_loss_w(fsw, bpk_t)
    v_rms = vin * math.sqrt(max(0.1, (T / 2.0 - t_dead) / (T / 2.0)))
    rcore = (v_rms ** 2) / max(1e-6, p_core)
    d_model = "D_1N5819" if diode_mode == "SCHOTTKY" else "D_UF4007"
    v_init = vin - (0.65 if diode_mode == "SCHOTTKY" else 1.35)
    n_cyc = 200
    t_end = n_cyc * T
    t_m1 = (n_cyc - 10) * T

    cir = f"""* As-Routed EE22/08/13 (PC95) 2-Layer Reversible 1:1 (12T:12T) — ngspice-46
* Case: {name} | Vin={vin:.2f}V, fsw={fsw/1e3:.0f}kHz, Iload={iload*1e3:.2f}mA, AL={al_nh}nH/T2 (Lm={lm*1e6:.1f}uH), Diode={d_model}
* As-routed 60C params: R_ac={r_ac:.3f}ohm (Fr={fr:.4f}), Llk={L_LK*1e6:.2f}uH, Cww={C_WW*1e12:.1f}pF, Bpk={bpk_mt:.1f}mT, Pcore={p_core*1e3:.2f}mW
.options reltol=5e-4 abstol=1e-10 vntol=1e-5 method=gear
.model D_1N5819 D(IS=2.5e-6 N=1.08 RS=0.25 CJO=110p TT=5n BV=40 IBV=1m)
.model D_UF4007 D(IS=2.0e-9 N=1.75 RS=0.35 CJO=17p TT=50n BV=1000 IBV=10u)

Vleg1 leg1_i 0 PULSE(0 {vin:.4f} 0 {t_edge:.3e} {t_edge:.3e} {t_on:.6e} {T:.6e})
Vleg2 leg2_i 0 PULSE(0 {vin:.4f} {T/2:.6e} {t_edge:.3e} {t_edge:.3e} {t_on:.6e} {T:.6e})
Rdrv1 leg1_i p1_in 0.25
Rdrv2 leg2_i p2_in 0.25

Rpri p1_in p1_r {r_ac:.4f}
Llk  p1_r  p1_m {L_LK:.4e}
Lp   p1_m  p2_in {lm:.4e}
Rcore p1_m p2_in {rcore:.1f}

Ls   s1_m  s2_m {lm:.4e}
Rsec s1_m  ac1  {r_ac:.4f}
Rs2  s2_m  ac2  1m
K1   Lp Ls 0.999999

Cww1 p1_in ac1 {C_WW/2:.3e}
Cww2 p2_in ac2 {C_WW/2:.3e}
Riso gnd_iso 0 1G

D1 ac1 vrect {d_model}
D2 ac2 vrect {d_model}
D3 gnd_iso ac1 {d_model}
D4 gnd_iso ac2 {d_model}
Cflt vrect cflt_e 4.7u IC={v_init:.3f}
Resr cflt_e gnd_iso 0.15
Iload vrect gnd_iso {iload:.6e}

.control
tran {T/40:.4e} {t_end:.4e} 0 {T/40:.4e} uic
let vrect_diff = v(vrect) - v(gnd_iso)
let ip_abs = abs(i(Vleg1))
let pin_v = -(v(leg1_i)*i(Vleg1) + v(leg2_i)*i(Vleg2))
let pout_v = vrect_diff * {iload:.6e}
meas tran vrect_min min vrect_diff from={t_m1:.4e} to={t_end:.4e}
meas tran vrect_avg avg vrect_diff from={t_m1:.4e} to={t_end:.4e}
meas tran vrect_max max vrect_diff from={t_m1:.4e} to={t_end:.4e}
meas tran ip_pk max ip_abs from={t_m1:.4e} to={t_end:.4e}
meas tran p_in avg pin_v from={t_m1:.4e} to={t_end:.4e}
meas tran p_out avg pout_v from={t_m1:.4e} to={t_end:.4e}
.endc
.end
"""
    cir_path = os.path.join(SIM_DIR, f"{name}.cir")
    log_path = os.path.join(SIM_DIR, f"{name}.log")
    with open(cir_path, "w", encoding="utf-8") as f:
        f.write(cir)
    log_lines.clear()
    ng.ngSpice_Command(b"destroy all")
    ng.ngSpice_Command(b"remcirc")
    ng.ngSpice_Command(f"source {cir_path.replace(os.sep, '/')}".encode("utf-8"))
    out = "\n".join(log_lines)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(out)
    res = {"bpk_mt": bpk_mt, "pcore_mw": p_core * 1e3}
    for k in ("vrect_min", "vrect_avg", "vrect_max", "ip_pk", "p_in", "p_out"):
        m = re.search(rf"\b{k}\s*=\s*([+-]?[0-9.eE+-]+)", out)
        res[k] = float(m.group(1)) if m else float("nan")
    return res

def main():
    print(f"As-routed EE22 2L 1:1 (12T:12T) params: R_dc60={R_DC_60:.3f} ohm, Llk={L_LK*1e6:.2f} uH, Cww={C_WW*1e12:.1f} pF\n")
    cases = [
        ("E1_11p1V_200k_10mA_Lm900_SCH",   11.10, 200e3, 10.0e-3, 6250, "SCHOTTKY"),
        ("E2_11p1V_200k_1p2mA_Lm900_SCH",  11.10, 200e3,  1.2e-3, 6250, "SCHOTTKY"),
        ("E3_12p0V_200k_1p2mA_Lm720_SCH",  12.00, 200e3,  1.2e-3, 5000, "SCHOTTKY"),
        ("E4_12p0V_200k_10mA_Lm720_SCH",   12.00, 200e3, 10.0e-3, 5000, "SCHOTTKY"),
        ("E5_12p0V_100k_1p2mA_Lm540_SCH",  12.00, 100e3,  1.2e-3, 3750, "SCHOTTKY"),
        ("E6_12p0V_50k_1p2mA_Lm540_SCH",   12.00,  50e3,  1.2e-3, 3750, "SCHOTTKY"),
        ("E7_12p6V_250k_0p05mA_Lm540_SCH", 12.60, 250e3, 0.05e-3, 3750, "SCHOTTKY"),
        ("E8_11p1V_150k_1p2mA_Lm720_UF4",  11.10, 150e3,  1.2e-3, 5000, "UF4007"),
    ]
    print(f"{'Case':32s} | {'Vrect_min':>9s} | {'Vrect_max':>9s} | {'Vgs_est':>8s} | {'Bpk(mT)':>7s} | {'Eff(%)':>6s} | {'Status'}")
    print("-" * 96)
    all_ok = True
    for name, vin, fsw, il, al, dm in cases:
        r = run_case(name, vin, fsw, il, al, dm)
        vgs_min = r["vrect_min"] - 0.70
        vgs_max = r["vrect_max"] - 0.70
        eff = (100.0 * r["p_out"] / r["p_in"]) if r["p_in"] > 0 else 0.0
        ok = (vgs_min >= 9.0) and (vgs_max <= 18.0) and (r["bpk_mt"] < 200.0)
        if not ok:
            all_ok = False
        print(f"{name:32s} | {r['vrect_min']:8.3f}V | {r['vrect_max']:8.3f}V | {vgs_min:7.2f}V | {r['bpk_mt']:7.1f} | {eff:5.1f}% | {'PASS' if ok else 'FAIL'}")
    if not all_ok:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
