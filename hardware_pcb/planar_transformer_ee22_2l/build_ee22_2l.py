"""
2-Layer Reversible-Stack 1:1 (12T : 12T) Planar Transformer Module Builder (KiCad 10.0.6) — Rev 1.0 Production
Core: Standard EE22/08/13 (PC95 Mn-Zn ferrite)
  - A = 22.30 +-0.30 mm, B = 8.30 +-0.30 mm (16.60 mated), C = 12.90 +-0.25 mm
  - D = 5.40 +-0.30 mm (10.80 mated window H), E = 15.50 mm min, F = 5.60 +-0.20 mm
  - Ae = 72.7 mm^2, le = 40.6 mm, Ve = 2950 mm^3, AL ~ 5000 nH/T^2 ungapped PC95

Reversible 1-Gerber Architecture (Order ONE 2-layer 0.80 mm 1oz PCB -> stack 2 identical boards per channel!):
  - Board outline: 30.00 x 28.00 mm (100% Y-symmetric around YC = 14.00 mm!)
  - Mating interface: 1x4 (2.54 mm pitch) matching friend's mosfet_gate_driver (a00c78f) J14 / J15 / J16:
      * Pin 1 (Y = 10.19): 1.60 mm PTH pad (1.00 mm drill) -> Winding Terminal 1 (/W_1)
      * Pin 2 (Y = 12.73): 1.60 mm PTH pad (1.00 mm drill) -> Winding Terminal 2 (/W_2)
      * Pin 3 (Y = 15.27): 1.80 mm NPTH clearance hole (ZERO copper, swallows mating pin/fillet untouched!)
      * Pin 4 (Y = 17.81): 1.80 mm NPTH clearance hole (ZERO copper)
  - Assembly of 1 Transformer (1:1 ratio, 12T : 12T, ZERO jumper wires):
      * Board 1 (Normal, F.Cu UP)          -> Pins 1 & 2 = Primary  (/Trans_in1, /Trans_in2); Pins 3 & 4 pass through NPTH
      * 0.10 mm Kapton insulation sheet    -> Separates Board 1 and Board 2 (> 4 kV dielectric!)
      * Board 2 (Flipped 180 deg in Y)     -> Pins 3 & 4 = Secondary (/Trans_A,  /Trans_B);  Pins 1 & 2 pass through NPTH
      * All 3 milled core cutouts & outer edges map onto themselves to 0.0000 mm precision when flipped!
      * Inner join vias automatically offset to opposite ends of center cutout (+8.05 mm vs -8.05 mm = 16.10 mm apart!)
  - Winding per 2-layer board (12T CW, 1 oz = 35 um Cu on BOTH layers):
      * L1 (F.Cu, 35 um): 6T inward CW  (420 um W / 220 um G, 0.365 mm slot clearance!)
      * L2 (B.Cu, 35 um): 6T outward CW (420 um W / 220 um G, 0.365 mm slot clearance!)
      * V_JOIN: 0.80 mm pad / 0.40 mm drill (0.20 mm annular ring, tented) at (XC_CORE, YC + 8.05) -> 0.400 mm to center slot!
  - Milled EE22 Cutouts (Edge.Cuts):
      * Center slot: 6.30 x 14.50 mm (clears max 5.80 x 13.15 mm center leg even with D=2.0 mm CNC bit @ -0.20mm tol by +0.050 mm!)
      * Outer slots: 2x 4.30 x 14.50 mm at dx = +-7.50..11.80 mm (clears E_min=15.50 & A_max=22.60 even with D=2.0 mm bit by +0.050 mm!)
"""
import json
import math
import os
import uuid

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

def det_uuid(tag: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"planar-transformer-ee22-2l-v10:{tag}"))

# Board & Core Center Geometry (mm) — 100% Y-symmetric around YC = 14.00 mm!
BOARD_W = 30.00
BOARD_H = 28.00
XC_CORE = 16.80  # Core center X (left header at X = 2.00 -> dx_hdr = -14.80; right edge at 30.00 -> +13.20)
YC = BOARD_H / 2.0  # 14.00 mm

DX_HDR = -14.80  # X = 2.00 mm from left PCB edge
HDR_X = XC_CORE + DX_HDR  # 2.00 mm
# 1x4 header pin Y offsets (exact 2.54 mm pitch, 100% Y-symmetric around YC!)
PIN_Y_OFFS = [-3.81, -1.27, +1.27, +3.81]  # Y = 10.19, 12.73, 15.27, 17.81 mm

# Milled EE22/08/13 Core Cutouts (relative to XC_CORE, YC) — 100% Y-symmetric!
# Center leg max 5.80 x 13.15 mm -> 6.30 x 14.50 mm (+0.050 mm corner clearance even at D=2.0 mm CNC bit @ -0.20mm tol!)
# Outer legs E_min=15.50 (7.75), A_max=22.60 (11.30) -> +-7.50..+-11.80 (4.30 x 14.50 mm, +0.050 mm at D=2.0 mm bit!)
CUTOUTS = [
    (-3.15, -7.25, +3.15, +7.25),   # Center leg (6.30 x 14.50 mm)
    (-11.80, -7.25, -7.50, +7.25),  # Left outer leg (4.30 x 14.50 mm)
    (+7.50, -7.25, +11.80, +7.25),  # Right outer leg (4.30 x 14.50 mm)
]

# Inner Join Via (relative to XC_CORE, YC) — 0.80 mm pad / 0.40 mm drill (0.20 mm annular ring!)
# Top edge = 8.05 - 0.40 = 7.65 mm -> 0.400 mm clear of center cutout (7.25 mm)!
V_JOIN = (0.00, +8.05)

# Winding Parameters (1 oz = 35 um Cu on BOTH F.Cu and B.Cu, 6T per layer = 12T per board)
W = 0.420      # Track width (mm, 16.5 mil)
G = 0.220      # Track gap (mm, 8.7 mil)
P = W + G      # 0.640 mm pitch
N_LAYER = 6
X0 = 3.725     # Inner Cu edge = 3.725 - 0.210 = 3.515 -> 0.365 mm to center slot (3.150) AND 0.365 mm to outer slot (7.500)!
Y0 = 8.950     # Inner Cu edge = 8.950 - 0.210 = 8.740 -> 1.490 mm to center slot (7.250), 0.90 mm diagonal into V_JOIN (8.05)!
C0 = 0.380     # Inner chamfer

SQRT2 = math.sqrt(2.0)

# Net-tie / coil anchor coordinates (relative to XC_CORE, YC)
# Placed cleanly in the 2.10 mm corridor between left header (right edge -13.90) and left cutout (-11.80)
ANCHOR_START = (-12.85, -3.81)  # F.Cu pad "1" -> connects to J1.1 (-14.80, -3.81)
ANCHOR_END   = (-12.85, -1.27)  # B.Cu pad "1" -> net-tie bar to B.Cu pad "2" (-13.65, -1.27) -> J1.2 (-14.80, -1.27)
ANCHOR_P2    = (-13.65, -1.27)

def poly_to_segs(pts):
    segs = []
    for a, b in zip(pts[:-1], pts[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
            segs.append((a, b))
    return segs

def build_L1_inward_cw():
    """
    L1 (F.Cu): 6T inward CW from ANCHOR_START (-12.85, -3.81) to V_JOIN (0.00, +8.05).
    Routes cleanly down left corridor at dx = -12.85 (0.84 mm clear of -11.80 cutout AND 0.84 mm clear of H1-H4!)
    """
    xk = [X0 + k * P for k in range(N_LAYER)]
    yk = [Y0 + k * P for k in range(N_LAYER)]
    ck = [C0 + k * P * (2.0 - SQRT2) for k in range(N_LAYER)]

    # Enter outermost turn k=5 on bottom bar going LEFT -> UP left side (CW!)
    # Left corridor at x = -12.85 goes down from -3.81 to yk[5] - 1.00, then 45 deg into bottom bar yk[5]
    pts = [
        ANCHOR_START,
        (-12.85, yk[5] - 1.00),
        (-11.85, yk[5]),
        (-xk[5] + ck[5], yk[5]),
    ]
    # Exact-pitch 45-deg step-in jogs on bottom bar:
    # Turn 0 exits (+0.90, +8.95) -> (0.00, +8.05): line x - y = -8.05
    # Set xj1 = +0.55 -> k=1 line: x - y = 0.55 - 9.59 = -9.04 -> perp dist = 0.99 / sqrt(2) = 0.700 mm (280 um gap > 220 um!)
    xj1 = 0.55
    for k in range(N_LAYER - 1, -1, -1):
        pts.extend([
            (-xk[k], yk[k] - ck[k]),
            (-xk[k], -yk[k] + ck[k]),
            (-xk[k] + ck[k], -yk[k]),
            (+xk[k] - ck[k], -yk[k]),
            (+xk[k], -yk[k] + ck[k]),
            (+xk[k], +yk[k] - ck[k]),
            (+xk[k] - ck[k], +yk[k]),
        ])
        if k > 0:
            xjk = xj1 - (k - 1) * P * (SQRT2 - 1.0)
            pts.extend([
                (xjk, yk[k]),
                (xjk - P, yk[k - 1]),
                (-xk[k - 1] + ck[k - 1], yk[k - 1]),
            ])
        else:
            dy_v = yk[0] - V_JOIN[1]  # 0.90 mm
            pts.extend([
                (V_JOIN[0] + dy_v, yk[0]),
                V_JOIN,
            ])
    return poly_to_segs(pts)

def build_L2_outward_cw():
    """
    L2 (B.Cu): 6T outward CW from V_JOIN (0.00, +8.05) to ANCHOR_END (-12.85, -1.27).
    """
    xk = [X0 + k * P for k in range(N_LAYER)]
    yk = [Y0 + k * P for k in range(N_LAYER)]
    ck = [C0 + k * P * (2.0 - SQRT2) for k in range(N_LAYER)]

    dy_v = yk[0] - V_JOIN[1]  # 0.90 mm
    pts = [
        V_JOIN,
        (V_JOIN[0] - dy_v, yk[0]),
        (-xk[0] + ck[0], yk[0]),
    ]
    xj0 = 0.55
    for k in range(N_LAYER):
        pts.extend([
            (-xk[k], yk[k] - ck[k]),
            (-xk[k], -yk[k] + ck[k]),
            (-xk[k] + ck[k], -yk[k]),
            (+xk[k] - ck[k], -yk[k]),
            (+xk[k], -yk[k] + ck[k]),
            (+xk[k], +yk[k] - ck[k]),
            (+xk[k] - ck[k], +yk[k]),
        ])
        xjk = xj0 + k * P * (SQRT2 - 1.0)
        if k < N_LAYER - 1:
            pts.extend([
                (xjk, yk[k]),
                (xjk - P, yk[k + 1]),
                (-xk[k + 1] + ck[k + 1], yk[k + 1]),
            ])
        else:
            y_out = yk[5] + P  # 12.79 mm -> outer Cu edge 13.00 mm (1.00 mm clear of 14.00 mm board edge!)
            pts.extend([
                (xjk, yk[5]),
                (xjk - P, y_out),
                (-11.85, y_out),
                (-12.85, y_out - 1.00),
                ANCHOR_END,
            ])
    return poly_to_segs(pts)

def seg_dist(a1, a2, b1, b2):
    def pt_seg(p, s1, s2):
        dx, dy = s2[0] - s1[0], s2[1] - s1[1]
        l2 = dx * dx + dy * dy
        if l2 < 1e-12:
            return math.hypot(p[0] - s1[0], p[1] - s1[1])
        t = max(0.0, min(1.0, ((p[0] - s1[0]) * dx + (p[1] - s1[1]) * dy) / l2))
        return math.hypot(p[0] - (s1[0] + t * dx), p[1] - (s1[1] + t * dy))
    def ccw(p1, p2, p3):
        return (p3[1] - p1[1]) * (p2[0] - p1[0]) > (p2[1] - p1[1]) * (p3[0] - p1[0])
    if (ccw(a1, b1, b2) != ccw(a2, b1, b2)) and (ccw(a1, a2, b1) != ccw(a1, a2, b2)):
        return 0.0
    return min(pt_seg(a1, b1, b2), pt_seg(a2, b1, b2), pt_seg(b1, a1, a2), pt_seg(b2, a1, a2))

def check_layer_self_clearance(name, segs, width_mm):
    min_gap = 1e9
    n = len(segs)
    for i in range(n):
        for j in range(i + 3, n):
            d = seg_dist(segs[i][0], segs[i][1], segs[j][0], segs[j][1])
            g = d - width_mm
            if g < min_gap:
                min_gap = g
    tot_len = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs)
    print(f"  {name:18s}: {n:3d} segs, len={tot_len:6.2f} mm, min_turn_gap={min_gap*1000:6.2f} um")
    return min_gap, tot_len

def write_fp_sym_tables():
    with open(os.path.join(OUT_DIR, "fp-lib-table"), "w", encoding="utf-8") as f:
        f.write('(fp_lib_table\n  (version 7)\n  (lib (name "ee22_lib")(type "KiCad")(uri "${KIPRJMOD}/ee22_lib.pretty")(options "")(descr "Local EE22x13 2-layer planar transformer footprints"))\n)\n')
    with open(os.path.join(OUT_DIR, "sym-lib-table"), "w", encoding="utf-8") as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "ee22_lib")(type "KiCad")(uri "${KIPRJMOD}/ee22_lib.kicad_sym")(options "")(descr "Local EE22x13 2-layer planar transformer symbols"))\n)\n')

def write_symbol_lib():
    sym = '''(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor") (generator_version "10.0")
\t(symbol "Planar_Winding_EE22_12T"
\t\t(pin_names (offset 1.016) (hide yes))
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(in_pos_files yes)
\t\t(duplicate_pin_numbers_are_jumpers no)
\t\t(property "Reference" "L" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
\t\t(property "Value" "EE22_13_PC95_12T" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
\t\t(property "Footprint" "ee22_lib:Planar_EE22_13_12T_2L" (at 0 -7.62 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Datasheet" "EE22/08/13 PC95 Mn-Zn Ferrite Core" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Description" "2-Layer 12T Planar Winding Board for EE22/08/13 PC95 Core (stack 2 identical boards flipped 180 deg for 1:1 12T:12T transformer)" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(symbol "Planar_Winding_EE22_12T_0_1"
\t\t\t(polyline (pts (xy 0.508 3.81) (xy 0.508 -3.81)) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t(polyline (pts (xy 1.27 3.81) (xy 1.27 -3.81)) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t(arc (start -2.54 3.81) (mid -1.27 2.54) (end -2.54 1.27) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t(arc (start -2.54 1.27) (mid -1.27 0) (end -2.54 -1.27) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t(arc (start -2.54 -1.27) (mid -1.27 -2.54) (end -2.54 -3.81) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t(circle (center -3.556 3.556) (radius 0.35) (stroke (width 0.254) (type default)) (fill (type outline)))
\t\t)
\t\t(symbol "Planar_Winding_EE22_12T_1_1"
\t\t\t(pin passive line (at -5.08 3.81 0) (length 2.54) (name "W1" (effects (font (size 1.016 1.016)))) (number "1" (effects (font (size 1.016 1.016)))))
\t\t\t(pin passive line (at -5.08 -3.81 0) (length 2.54) (name "W2" (effects (font (size 1.016 1.016)))) (number "2" (effects (font (size 1.016 1.016)))))
\t\t)
\t\t(embedded_fonts no)
\t)
\t(symbol "Header_1x04_Reversible_2Pin"
\t\t(pin_names (offset 1.016) (hide yes))
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(in_pos_files yes)
\t\t(duplicate_pin_numbers_are_jumpers no)
\t\t(property "Reference" "J" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
\t\t(property "Value" "Conn_1x4_Rev_J14_J16" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
\t\t(property "Footprint" "ee22_lib:PinHeader_1x04_Reversible_2L" (at 0 -7.62 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Datasheet" "https://www.we-online.com/components/products/datasheet/61300411021.pdf" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Description" "1x4 2.54mm Reversible Stack Header (Pins 1-2 active 1.56/1.00mm PTH, Pins 3-4 isolated 1.80mm NPTH pass-through holes)" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(symbol "Header_1x04_Reversible_2Pin_0_1"
\t\t\t(polyline (pts (xy -2.54 3.81) (xy 2.54 3.81) (xy 2.54 -3.81) (xy -2.54 -3.81) (xy -2.54 3.81)) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t)
\t\t(symbol "Header_1x04_Reversible_2Pin_1_1"
\t\t\t(pin passive line (at 5.08 2.54 180) (length 2.54) (name "W1" (effects (font (size 1.016 1.016)))) (number "1" (effects (font (size 1.016 1.016)))))
\t\t\t(pin passive line (at 5.08 -2.54 180) (length 2.54) (name "W2" (effects (font (size 1.016 1.016)))) (number "2" (effects (font (size 1.016 1.016)))))
\t\t)
\t\t(embedded_fonts no)
\t)
)
'''
    with open(os.path.join(OUT_DIR, "ee22_lib.kicad_sym"), "w", encoding="utf-8") as f:
        f.write(sym)

def write_footprints():
    fp_dir = os.path.join(OUT_DIR, "ee22_lib.pretty")
    os.makedirs(fp_dir, exist_ok=True)

    t_mod = '''(footprint "Planar_EE22_13_12T_2L"
\t(version 20241229)
\t(generator "pcbnew")
\t(generator_version "10.0")
\t(layer "F.Cu")
\t(descr "EE22/08/13 (PC95) 2-Layer 12T Reversible Planar Winding Board (stack 2 boards flipped 180 deg for 1:1 12T:12T)")
\t(tags "planar transformer EE22 PC95 2-layer 12T reversible")
\t(attr smd)
\t(net_tie_pad_groups "1,2")
\t(property "Reference" "T1" (at 0 -13.15 0) (layer "F.SilkS") (effects (font (size 0.85 0.85) (thickness 0.16))))
\t(property "Value" "EE22_13_PC95_12T" (at 0 13.45 0) (layer "F.Fab") (effects (font (size 0.80 0.80) (thickness 0.15))))
\t(property "Datasheet" "EE22/08/13 PC95 Mn-Zn Ferrite Core" (at 0 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1.0 1.0) (thickness 0.15))))
\t(fp_rect (start -11.15 -6.45) (end 11.15 6.45) (stroke (width 0.12) (type solid)) (fill none) (layer "F.Fab"))
\t(fp_rect (start -11.15 -6.45) (end 11.15 6.45) (stroke (width 0.12) (type solid)) (fill none) (layer "B.Fab"))
\t(fp_rect (start -2.80 -6.45) (end 2.80 6.45) (stroke (width 0.10) (type dash)) (fill none) (layer "F.Fab"))
\t(fp_rect (start -12.10 -13.30) (end 12.10 13.30) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
\t(fp_rect (start -12.10 -13.30) (end 12.10 13.30) (stroke (width 0.05) (type solid)) (fill none) (layer "B.CrtYd"))
\t(fp_rect (start -11.50 -6.80) (end -7.75 6.80) (stroke (width 0.10) (type dash)) (fill none) (layer "Dwgs.User"))
\t(fp_rect (start 7.75 -6.80) (end 11.50 6.80) (stroke (width 0.10) (type dash)) (fill none) (layer "Dwgs.User"))
\t(fp_text user "EE22/08/13 PC95: 0.10mm KAPTON BETWEEN 2 IDENTICAL BOARDS (FLIP TOP BOARD 180 DEG)" (at 0 15.20 0) (layer "Dwgs.User") (effects (font (size 0.65 0.65) (thickness 0.12))))
\t(fp_line (start 12.15 -7.40) (end 12.15 7.40) (stroke (width 0.16) (type solid)) (layer "F.SilkS"))
\t(fp_line (start 12.15 -7.40) (end 12.15 7.40) (stroke (width 0.16) (type solid)) (layer "B.SilkS"))
\t(fp_line (start -12.85 -1.27) (end -13.65 -1.27) (stroke (width 0.45) (type solid)) (layer "B.Cu"))
\t(pad "1" smd rect (at -12.85 -3.81) (size 0.50 0.50) (layers "F.Cu"))
\t(pad "1" smd rect (at -12.85 -1.27) (size 0.50 0.50) (layers "B.Cu"))
\t(pad "2" smd rect (at -13.65 -1.27) (size 0.50 0.50) (layers "B.Cu"))
)
'''
    with open(os.path.join(fp_dir, "Planar_EE22_13_12T_2L.kicad_mod"), "w", encoding="utf-8") as f:
        f.write(t_mod)

    # Reversible 1x4 2.54mm header footprint centered at (0, 0) -> Pins at y = -3.81, -1.27, +1.27, +3.81
    # Pin 1 & 2: 1.56mm PTH pads (1.00mm drill -> 0.28mm annular ring; Pad 1 roundrect rratio=0.34 -> 1.767mm max diag < 1.80mm NPTH!)
    # Pin 3 & 4: 1.80mm NPTH clearance holes (ZERO copper -> 0.86mm gap to Pin 2 pad, 0.74mm FR4 web between H3 & H4!)
    j_mod = '''(footprint "PinHeader_1x04_Reversible_2L"
\t(version 20241229)
\t(generator "pcbnew")
\t(generator_version "10.0")
\t(layer "F.Cu")
\t(descr "1x4 2.54mm Reversible Stack Header (Pins 1-2 active 1.56/1.00mm PTH, Pins 3-4 isolated 1.80mm NPTH pass-through)")
\t(tags "pin header 1x04 2.54mm reversible stackable NPTH")
\t(property "Reference" "J1" (at 0 -6.95 0) (layer "F.SilkS") (effects (font (size 0.85 0.85) (thickness 0.16))))
\t(property "Value" "Conn_1x4_Rev_J14_J16" (at 0 6.60 0) (layer "F.Fab") (hide yes) (effects (font (size 0.85 0.85) (thickness 0.15))))
\t(property "Datasheet" "https://www.we-online.com/components/products/datasheet/61300411021.pdf" (at 0 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1.0 1.0) (thickness 0.15))))
\t(attr through_hole)
\t(duplicate_pad_numbers_are_jumpers no)
\t(fp_rect (start -1.35 -5.18) (end 1.35 5.18) (stroke (width 0.16) (type solid)) (fill none) (layer "F.SilkS"))
\t(fp_rect (start -1.35 -5.18) (end 1.35 5.18) (stroke (width 0.16) (type solid)) (fill none) (layer "B.SilkS"))
\t(fp_line (start -1.35 -2.54) (end 1.35 -2.54) (stroke (width 0.16) (type solid)) (layer "F.SilkS"))
\t(fp_line (start -1.35 -2.54) (end 1.35 -2.54) (stroke (width 0.16) (type solid)) (layer "B.SilkS"))
\t(fp_line (start -1.35 0.00) (end 1.35 0.00) (stroke (width 0.16) (type solid)) (layer "F.SilkS"))
\t(fp_line (start -1.35 0.00) (end 1.35 0.00) (stroke (width 0.16) (type solid)) (layer "B.SilkS"))
\t(fp_circle (center 0.00 -5.65) (end 0.30 -5.65) (stroke (width 0.18) (type solid)) (fill solid) (layer "F.SilkS"))
\t(fp_circle (center 0.00 -5.65) (end 0.30 -5.65) (stroke (width 0.18) (type solid)) (fill solid) (layer "B.SilkS"))
\t(fp_rect (start -1.55 -5.40) (end 1.55 5.40) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
\t(fp_rect (start -1.55 -5.40) (end 1.55 5.40) (stroke (width 0.05) (type solid)) (fill none) (layer "B.CrtYd"))
\t(fp_rect (start -1.27 -5.08) (end 1.27 5.08) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab"))
\t(pad "1" thru_hole roundrect (at 0 -3.81) (size 1.56 1.56) (drill 1.00) (layers "*.Cu" "*.Mask") (roundrect_rratio 0.34) (remove_unused_layers no))
\t(pad "2" thru_hole circle (at 0 -1.27) (size 1.56 1.56) (drill 1.00) (layers "*.Cu" "*.Mask") (remove_unused_layers no))
\t(pad "" np_thru_hole circle (at 0 1.27) (size 1.80 1.80) (drill 1.80) (layers "*.Cu" "*.Mask"))
\t(pad "" np_thru_hole circle (at 0 3.81) (size 1.80 1.80) (drill 1.80) (layers "*.Cu" "*.Mask"))
\t(embedded_fonts no)
)
'''
    with open(os.path.join(fp_dir, "PinHeader_1x04_Reversible_2L.kicad_mod"), "w", encoding="utf-8") as f:
        f.write(j_mod)

def write_dru():
    dru = '''(version 1)

(rule "Winding_Track_Width_2L"
  (constraint track_width (min 0.420mm))
  (condition "A.NetClass == 'Planar_Winding'")
)

(rule "Winding_Clearance_2L"
  (constraint clearance (min 0.215mm))
  (condition "A.NetClass == 'Planar_Winding'")
)

(rule "Via_Annular_and_Drill_2L_Rugged"
  (constraint annular_width (min 0.15mm))
  (constraint hole_size (min 0.35mm))
  (condition "A.Type == 'Via'")
)

(rule "Copper_to_Milled_Cutout_Production"
  (constraint edge_clearance (min 0.35mm))
  (condition "A.Type == 'Track' || A.Type == 'Via'")
)
'''
    with open(os.path.join(OUT_DIR, "planar_transformer_ee22_2l.kicad_dru"), "w", encoding="utf-8") as f:
        f.write(dru)

def write_kicad_pro():
    src_pro = os.path.join(OUT_DIR, "..", "planar_transformer_module", "planar_transformer_module.kicad_pro")
    with open(src_pro, "r", encoding="utf-8") as f:
        pro = json.load(f)
    pro["meta"]["filename"] = "planar_transformer_ee22_2l.kicad_pro"
    pro["board"]["design_settings"]["rules"]["min_clearance"] = 0.200
    pro["board"]["design_settings"]["rules"]["min_track_width"] = 0.250
    pro["board"]["design_settings"]["rules"]["min_copper_edge_clearance"] = 0.35
    pro["board"]["design_settings"]["rules"]["min_hole_clearance"] = 0.30
    pro["board"]["design_settings"]["rules"]["min_via_annular_width"] = 0.15
    pro["board"]["design_settings"]["rules"]["min_via_diameter"] = 0.60
    pro["board"]["design_settings"]["rules"]["min_through_hole_diameter"] = 0.30
    pro["board"]["design_settings"]["rules"]["min_text_thickness"] = 0.15
    pro["board"]["design_settings"]["rules"]["min_text_height"] = 0.80

    pro["net_settings"]["classes"] = [
        {
            "bus_width": 12, "clearance": 0.22, "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.2, "diff_pair_width": 0.2,
            "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": "Default",
            "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647, "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": 0.42, "tuning_profile": "", "via_diameter": 0.8, "via_drill": 0.4, "wire_width": 6
        },
        {
            "bus_width": 12, "clearance": 0.215, "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.2, "diff_pair_width": 0.2,
            "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": "Planar_Winding",
            "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 1, "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": 0.42, "tuning_profile": "", "via_diameter": 0.8, "via_drill": 0.4, "wire_width": 6
        },
    ]
    pro["net_settings"]["netclass_assignments"] = {
        "/W_1": ["Planar_Winding"],
        "/W_2": ["Planar_Winding"],
    }
    pro["net_settings"]["netclass_patterns"] = [
        {"netclass": "Planar_Winding", "pattern": "/W_*"},
    ]
    sheet_uuid = det_uuid("root-sheet")
    pro["schematic"]["top_level_sheets"] = [
        {"filename": "planar_transformer_ee22_2l.kicad_sch", "name": "planar_transformer_ee22_2l", "uuid": sheet_uuid}
    ]
    with open(os.path.join(OUT_DIR, "planar_transformer_ee22_2l.kicad_pro"), "w", encoding="utf-8") as f:
        json.dump(pro, f, indent=2)

def write_schematic():
    sheet_uuid = det_uuid("root-sheet")
    sch = f'''(kicad_sch
\t(version 20260101)
\t(generator "eeschema")
\t(generator_version "10.0")
\t(uuid "{sheet_uuid}")
\t(paper "A4")
\t(title_block
\t\t(title "EE22/08/13 (PC95) 2L 1:1 Reversible Planar Transformer")
\t\t(date "2026-11-25")
\t\t(rev "1.0")
\t\t(company "BMS Reconfiguration Hardware")
\t\t(comment 1 "Stack 2 identical 0.8mm 2L boards (flip top 180 deg) -> 12T:12T (1:1)")
\t\t(comment 2 "1x4 header matches mosfet_gate_driver J14-J16 | 1oz Cu | >=0.365mm clr")
\t)
\t(lib_symbols
\t\t(symbol "ee22_lib:Planar_Winding_EE22_12T"
\t\t\t(pin_names (offset 1.016) (hide yes))
\t\t\t(exclude_from_sim no)
\t\t\t(in_bom yes)
\t\t\t(on_board yes)
\t\t\t(in_pos_files yes)
\t\t\t(duplicate_pin_numbers_are_jumpers no)
\t\t\t(property "Reference" "L" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
\t\t\t(property "Value" "EE22_13_PC95_12T" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
\t\t\t(property "Footprint" "ee22_lib:Planar_EE22_13_12T_2L" (at 0 -7.62 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(property "Datasheet" "EE22/08/13 PC95 Mn-Zn Ferrite Core" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(property "Description" "2-Layer 12T Planar Winding Board for EE22/08/13 PC95 Core (stack 2 identical boards flipped 180 deg for 1:1 12T:12T transformer)" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(symbol "Planar_Winding_EE22_12T_0_1"
\t\t\t\t(polyline (pts (xy 0.508 3.81) (xy 0.508 -3.81)) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t\t(polyline (pts (xy 1.27 3.81) (xy 1.27 -3.81)) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t\t(arc (start -2.54 3.81) (mid -1.27 2.54) (end -2.54 1.27) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t\t(arc (start -2.54 1.27) (mid -1.27 0) (end -2.54 -1.27) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t\t(arc (start -2.54 -1.27) (mid -1.27 -2.54) (end -2.54 -3.81) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t\t(circle (center -3.556 3.556) (radius 0.35) (stroke (width 0.254) (type default)) (fill (type outline)))
\t\t\t)
\t\t\t(symbol "Planar_Winding_EE22_12T_1_1"
\t\t\t\t(pin passive line (at -5.08 3.81 0) (length 2.54) (name "W1" (effects (font (size 1.016 1.016)))) (number "1" (effects (font (size 1.016 1.016)))))
\t\t\t\t(pin passive line (at -5.08 -3.81 0) (length 2.54) (name "W2" (effects (font (size 1.016 1.016)))) (number "2" (effects (font (size 1.016 1.016)))))
\t\t\t)
\t\t\t(embedded_fonts no)
\t\t)
\t\t(symbol "ee22_lib:Header_1x04_Reversible_2Pin"
\t\t\t(pin_names (offset 1.016) (hide yes))
\t\t\t(exclude_from_sim no)
\t\t\t(in_bom yes)
\t\t\t(on_board yes)
\t\t\t(in_pos_files yes)
\t\t\t(duplicate_pin_numbers_are_jumpers no)
\t\t\t(property "Reference" "J" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
\t\t\t(property "Value" "Conn_1x4_Rev_J14_J16" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
\t\t\t(property "Footprint" "ee22_lib:PinHeader_1x04_Reversible_2L" (at 0 -7.62 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(property "Datasheet" "https://www.we-online.com/components/products/datasheet/61300411021.pdf" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(property "Description" "1x4 2.54mm Reversible Stack Header (Pins 1-2 active 1.56/1.00mm PTH, Pins 3-4 isolated 1.80mm NPTH pass-through holes)" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(symbol "Header_1x04_Reversible_2Pin_0_1"
\t\t\t\t(polyline (pts (xy -2.54 3.81) (xy 2.54 3.81) (xy 2.54 -3.81) (xy -2.54 -3.81) (xy -2.54 3.81)) (stroke (width 0.254) (type default)) (fill (type none)))
\t\t\t)
\t\t\t(symbol "Header_1x04_Reversible_2Pin_1_1"
\t\t\t\t(pin passive line (at 5.08 2.54 180) (length 2.54) (name "W1" (effects (font (size 1.016 1.016)))) (number "1" (effects (font (size 1.016 1.016)))))
\t\t\t\t(pin passive line (at 5.08 -2.54 180) (length 2.54) (name "W2" (effects (font (size 1.016 1.016)))) (number "2" (effects (font (size 1.016 1.016)))))
\t\t\t)
\t\t\t(embedded_fonts no)
\t\t)
\t)
\t(wire (pts (xy 119.38 96.52) (xy 149.86 96.52)) (stroke (width 0) (type default)) (uuid "{det_uuid('w1')}"))
\t(wire (pts (xy 149.86 96.52) (xy 149.86 95.25)) (stroke (width 0) (type default)) (uuid "{det_uuid('w1b')}"))
\t(wire (pts (xy 119.38 101.60) (xy 149.86 101.60)) (stroke (width 0) (type default)) (uuid "{det_uuid('w2')}"))
\t(wire (pts (xy 149.86 101.60) (xy 149.86 102.87)) (stroke (width 0) (type default)) (uuid "{det_uuid('w2b')}"))
\t(label "W_1" (at 132.08 96.52 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{det_uuid('lbl_w1')}"))
\t(label "W_2" (at 132.08 101.60 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{det_uuid('lbl_w2')}"))
\t(text "EE22/08/13 (PC95) 2-LAYER REVERSIBLE-STACK 1:1 PLANAR TRANSFORMER — REV 1.0\\nONE SINGLE 2-LAYER PCB DESIGN -> STACK 2 IDENTICAL BOARDS PER TRANSFORMER (ZERO JUMPER WIRES):\\n  1. Board 1 (Bottom, F.Cu UP = PRIMARY): Solder Pins 1 & 2 (Trans_in1, Trans_in2); Pins 3 & 4 pass through 1.80mm NPTH.\\n  2. Insulation Barrier: Place 0.10mm Kapton tape sheet across Board 1 copper winding (>4 kV Pri-Sec isolation).\\n  3. Board 2 (Top, Flip 180 deg in Y, B.Cu UP = SECONDARY): Solder Pins 3 & 4 (Trans_A, Trans_B); Pins 1 & 2 pass through NPTH.\\n  4. Core: Assemble 1x pair EE22/08/13 (PC95) through the 3 milled cutouts (6.30x14.50 center, 2x 4.30x14.50 outer).\\nStackup: 2-Layer 0.80mm FR-4, 1oz (35um) Cu on F.Cu & B.Cu | Winding: 12T CW (6T+6T, 420um W / 220um G, 0.365mm slot clr).\\nElectrical Spec (1:1, 12T:12T, Lm=720uH nom): Drive Trans_in1/in2 with bipolar +/-12V H-bridge (150-250 kHz)\\n  through 10uF 25V X7R DC-block + 4.7 ohm 0.25W damper -> V_rect = 11.75V DC -> V_GS = 11.05V (81.2% 3-ch eff, 1.82A inrush).\\nMates to mosfet_gate_driver (a00c78f) J14/J15/J16 (1x4, 2.54mm): Pin1=Trans_in1(Dot), Pin2=Trans_in2, Pin3=Trans_A(Dot), Pin4=Trans_B."
\t\t(exclude_from_sim no)
\t\t(at 53.34 116.84 0)
\t\t(effects (font (size 1.45 1.45)) (justify left top))
\t\t(uuid "{det_uuid('note1')}")
\t)
\t(symbol
\t\t(lib_id "ee22_lib:Header_1x04_Reversible_2Pin")
\t\t(at 114.30 99.06 0)
\t\t(unit 1)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid "{det_uuid('sym_J1')}")
\t\t(property "Reference" "J1" (at 114.30 92.71 0) (effects (font (size 1.27 1.27))))
\t\t(property "Value" "Conn_1x4_Rev_J14_J16" (at 114.30 106.68 0) (effects (font (size 1.27 1.27))))
\t\t(property "Footprint" "ee22_lib:PinHeader_1x04_Reversible_2L" (at 114.30 109.22 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Datasheet" "https://www.we-online.com/components/products/datasheet/61300411021.pdf" (at 114.30 99.06 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(pin "1" (uuid "{det_uuid('j1_p1')}"))
\t\t(pin "2" (uuid "{det_uuid('j1_p2')}"))
\t\t(instances (project "planar_transformer_ee22_2l" (path "/{sheet_uuid}" (reference "J1") (unit 1))))
\t)
\t(symbol
\t\t(lib_id "ee22_lib:Planar_Winding_EE22_12T")
\t\t(at 154.94 99.06 0)
\t\t(unit 1)
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid "{det_uuid('sym_T1')}")
\t\t(property "Reference" "T1" (at 154.94 91.44 0) (effects (font (size 1.27 1.27))))
\t\t(property "Value" "EE22_13_PC95_12T" (at 154.94 106.68 0) (effects (font (size 1.27 1.27))))
\t\t(property "Footprint" "ee22_lib:Planar_EE22_13_12T_2L" (at 154.94 109.22 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(property "Datasheet" "EE22/08/13 PC95 Mn-Zn Ferrite Core" (at 154.94 99.06 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t(pin "1" (uuid "{det_uuid('t1_p1')}"))
\t\t(pin "2" (uuid "{det_uuid('t1_p2')}"))
\t\t(instances (project "planar_transformer_ee22_2l" (path "/{sheet_uuid}" (reference "T1") (unit 1))))
\t)
\t(sheet_instances (path "/" (page "1")))
\t(embedded_fonts no)
)
'''
    with open(os.path.join(OUT_DIR, "planar_transformer_ee22_2l.kicad_sch"), "w", encoding="utf-8") as f:
        f.write(sch)

def fmt_j1_fp():
    sym_uuid = det_uuid("sym_J1")
    return f'''\t(footprint "ee22_lib:PinHeader_1x04_Reversible_2L"
\t\t(layer "F.Cu")
\t\t(uuid "{det_uuid('fp_J1')}")
\t\t(at {HDR_X:.4f} {YC:.4f})
\t\t(descr "1x4 2.54mm Reversible Stack Header (Pins 1-2 active 1.56/1.00mm PTH, Pins 3-4 isolated 1.80mm NPTH pass-through)")
\t\t(tags "pin header 1x04 2.54mm reversible stackable NPTH")
\t\t(property "Reference" "J1" (at 0 -6.95 0) (layer "F.SilkS") (uuid "{det_uuid('J1_ref')}") (effects (font (size 0.85 0.85) (thickness 0.16))))
\t\t(property "Value" "Conn_1x4_Rev_J14_J16" (at 0 6.60 0) (layer "F.Fab") (hide yes) (uuid "{det_uuid('J1_val')}") (effects (font (size 0.85 0.85) (thickness 0.15))))
\t\t(property "Datasheet" "https://www.we-online.com/components/products/datasheet/61300411021.pdf" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{det_uuid('J1_ds')}") (effects (font (size 1.0 1.0) (thickness 0.15))))
\t\t(path "/{sym_uuid}")
\t\t(attr through_hole)
\t\t(duplicate_pad_numbers_are_jumpers no)
\t\t(fp_rect (start -1.35 -5.18) (end 1.35 5.18) (stroke (width 0.16) (type solid)) (fill none) (layer "F.SilkS") (uuid "{det_uuid('j1_sk1')}"))
\t\t(fp_rect (start -1.35 -5.18) (end 1.35 5.18) (stroke (width 0.16) (type solid)) (fill none) (layer "B.SilkS") (uuid "{det_uuid('j1_sk2')}"))
\t\t(fp_line (start -1.35 -2.54) (end 1.35 -2.54) (stroke (width 0.16) (type solid)) (layer "F.SilkS") (uuid "{det_uuid('j1_sk3')}"))
\t\t(fp_line (start -1.35 -2.54) (end 1.35 -2.54) (stroke (width 0.16) (type solid)) (layer "B.SilkS") (uuid "{det_uuid('j1_sk4')}"))
\t\t(fp_line (start -1.35 0.00) (end 1.35 0.00) (stroke (width 0.16) (type solid)) (layer "F.SilkS") (uuid "{det_uuid('j1_sk5')}"))
\t\t(fp_line (start -1.35 0.00) (end 1.35 0.00) (stroke (width 0.16) (type solid)) (layer "B.SilkS") (uuid "{det_uuid('j1_sk6')}"))
\t\t(fp_circle (center 0.00 -5.65) (end 0.30 -5.65) (stroke (width 0.18) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{det_uuid('j1_d1')}"))
\t\t(fp_circle (center 0.00 -5.65) (end 0.30 -5.65) (stroke (width 0.18) (type solid)) (fill solid) (layer "B.SilkS") (uuid "{det_uuid('j1_d2')}"))
\t\t(fp_rect (start -1.55 -5.40) (end 1.55 5.40) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "{det_uuid('j1_cy1')}"))
\t\t(fp_rect (start -1.55 -5.40) (end 1.55 5.40) (stroke (width 0.05) (type solid)) (fill none) (layer "B.CrtYd") (uuid "{det_uuid('j1_cy2')}"))
\t\t(fp_rect (start -1.27 -5.08) (end 1.27 5.08) (stroke (width 0.10) (type solid)) (fill none) (layer "F.Fab") (uuid "{det_uuid('j1_fb1')}"))
\t\t(pad "1" thru_hole roundrect (at 0 -3.81) (size 1.56 1.56) (drill 1.00) (layers "*.Cu" "*.Mask") (roundrect_rratio 0.34) (remove_unused_layers no) (net 1 "/W_1") (pinfunction "W1") (pintype "passive") (uuid "{det_uuid('j1_p1_pad')}"))
\t\t(pad "2" thru_hole circle (at 0 -1.27) (size 1.56 1.56) (drill 1.00) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net 2 "/W_2") (pinfunction "W2") (pintype "passive") (uuid "{det_uuid('j1_p2_pad')}"))
\t\t(pad "" np_thru_hole circle (at 0 1.27) (size 1.80 1.80) (drill 1.80) (layers "*.Cu" "*.Mask") (uuid "{det_uuid('j1_np3')}"))
\t\t(pad "" np_thru_hole circle (at 0 3.81) (size 1.80 1.80) (drill 1.80) (layers "*.Cu" "*.Mask") (uuid "{det_uuid('j1_np4')}"))
\t\t(embedded_fonts no)
\t)
'''

def fmt_t1_fp():
    sym_uuid = det_uuid("sym_T1")
    return f'''\t(footprint "ee22_lib:Planar_EE22_13_12T_2L"
\t\t(layer "F.Cu")
\t\t(uuid "{det_uuid('fp_T1')}")
\t\t(at {XC_CORE:.4f} {YC:.4f})
\t\t(descr "EE22/08/13 (PC95) 2-Layer 12T Reversible Planar Winding Board (stack 2 boards flipped 180 deg for 1:1 12T:12T)")
\t\t(tags "planar transformer EE22 PC95 2-layer 12T reversible")
\t\t(property "Reference" "T1" (at 0 -13.15 0) (layer "F.SilkS") (uuid "{det_uuid('T1_ref')}") (effects (font (size 0.85 0.85) (thickness 0.16))))
\t\t(property "Value" "EE22_13_PC95_12T" (at 0 13.45 0) (layer "F.Fab") (uuid "{det_uuid('T1_val')}") (effects (font (size 0.80 0.80) (thickness 0.15))))
\t\t(property "Datasheet" "EE22/08/13 PC95 Mn-Zn Ferrite Core" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{det_uuid('T1_ds')}") (effects (font (size 1.0 1.0) (thickness 0.15))))
\t\t(path "/{sym_uuid}")
\t\t(attr smd)
\t\t(net_tie_pad_groups "1,2")
\t\t(fp_rect (start -11.15 -6.45) (end 11.15 6.45) (stroke (width 0.12) (type solid)) (fill none) (layer "F.Fab") (uuid "{det_uuid('t1_fb1')}"))
\t\t(fp_rect (start -11.15 -6.45) (end 11.15 6.45) (stroke (width 0.12) (type solid)) (fill none) (layer "B.Fab") (uuid "{det_uuid('t1_fb2')}"))
\t\t(fp_rect (start -2.80 -6.45) (end 2.80 6.45) (stroke (width 0.10) (type dash)) (fill none) (layer "F.Fab") (uuid "{det_uuid('t1_fb3')}"))
\t\t(fp_rect (start -12.10 -13.30) (end 12.10 13.30) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid "{det_uuid('t1_cy1')}"))
\t\t(fp_rect (start -12.10 -13.30) (end 12.10 13.30) (stroke (width 0.05) (type solid)) (fill none) (layer "B.CrtYd") (uuid "{det_uuid('t1_cy2')}"))
\t\t(fp_rect (start -11.50 -6.80) (end -7.75 6.80) (stroke (width 0.10) (type dash)) (fill none) (layer "Dwgs.User") (uuid "{det_uuid('t1_g1')}"))
\t\t(fp_rect (start 7.75 -6.80) (end 11.50 6.80) (stroke (width 0.10) (type dash)) (fill none) (layer "Dwgs.User") (uuid "{det_uuid('t1_g2')}"))
\t\t(fp_text user "EE22/08/13 PC95: 0.10mm KAPTON BETWEEN 2 IDENTICAL BOARDS (FLIP TOP BOARD 180 DEG)" (at 0 15.20 0) (layer "Dwgs.User") (uuid "{det_uuid('t1_gt')}") (effects (font (size 0.65 0.65) (thickness 0.12))))
\t\t(fp_line (start 12.15 -7.40) (end 12.15 7.40) (stroke (width 0.16) (type solid)) (layer "F.SilkS") (uuid "{det_uuid('t1_sk1')}"))
\t\t(fp_line (start 12.15 -7.40) (end 12.15 7.40) (stroke (width 0.16) (type solid)) (layer "B.SilkS") (uuid "{det_uuid('t1_sk2')}"))
\t\t(fp_line (start -12.85 -1.27) (end -13.65 -1.27) (stroke (width 0.45) (type solid)) (layer "B.Cu") (uuid "{det_uuid('t1_nt1')}"))
\t\t(pad "1" smd rect (at -12.85 -3.81) (size 0.50 0.50) (layers "F.Cu") (net 1 "/W_1") (pinfunction "W1") (pintype "passive") (uuid "{det_uuid('t1_pad1a')}"))
\t\t(pad "1" smd rect (at -12.85 -1.27) (size 0.50 0.50) (layers "B.Cu") (net 1 "/W_1") (pinfunction "W1") (pintype "passive") (uuid "{det_uuid('t1_pad1b')}"))
\t\t(pad "2" smd rect (at -13.65 -1.27) (size 0.50 0.50) (layers "B.Cu") (net 2 "/W_2") (pinfunction "W2") (pintype "passive") (uuid "{det_uuid('t1_pad2')}"))
\t\t(embedded_fonts no)
\t)
'''

def write_pcb():
    l1_segs = build_L1_inward_cw()
    l2_segs = build_L2_outward_cw()

    print("Rev 1.0 EE22x13 2-Layer geometric self-clearance & length audit:")
    check_layer_self_clearance("L1 F.Cu (6T CW)", l1_segs, W)
    check_layer_self_clearance("L2 B.Cu (6T CW)", l2_segs, W)

    lead_segs = [
        ((DX_HDR, PIN_Y_OFFS[0]), ANCHOR_START, 0.55, "F.Cu", 1),
        ((DX_HDR, PIN_Y_OFFS[1]), ANCHOR_P2,    0.55, "B.Cu", 2),
    ]

    lines = []
    lines.append('''(kicad_pcb
\t(version 20260206)
\t(generator "pcbnew")
\t(generator_version "10.0")
\t(general
\t\t(thickness 0.80)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t)
\t(setup
\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.015) (epsilon_r 3.8))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (thickness 0.73) (material "FR4") (epsilon_r 4.5))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.015) (epsilon_r 3.8))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))
\t\t\t(copper_finish "HASL with lead-free solder")
\t\t\t(dielectric_constraints no)
\t\t)
\t\t(pad_to_mask_clearance 0)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(tenting (front yes) (back yes))
\t\t(covering (front no) (back no))
\t\t(plugging (front no) (back no))
\t\t(capping no)
\t\t(filling no)
\t)
\t(net 0 "")
\t(net 1 "/W_1")
\t(net 2 "/W_2")
''')

    lines.append(fmt_t1_fp())
    lines.append(fmt_j1_fp())

    # Outer board edge (Edge.Cuts): 30.00 x 28.00 mm
    lines.append(f'\t(gr_rect (start 0.0000 0.0000) (end {BOARD_W:.4f} {BOARD_H:.4f}) (stroke (width 0.05) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{det_uuid("edge_outer")}"))')

    # 3 Milled EE22/08/13 core cutouts (100% Y-symmetric around YC = 14.00 mm!)
    for idx, (x1, y1, x2, y2) in enumerate(CUTOUTS):
        lines.append(f'\t(gr_rect (start {XC_CORE+x1:.4f} {YC+y1:.4f}) (end {XC_CORE+x2:.4f} {YC+y2:.4f}) (stroke (width 0.05) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{det_uuid(f"cutout_{idx}")}"))')

    # Production silkscreen legends (>= 0.16 mm stroke, strictly clear of pads/edges/holes!)
    # F.SilkS faces UP on Board 1 (Primary); B.SilkS uses rot=180 + mirror so flipping Board 2 180 deg around horizontal X-axis makes EVERY label read right-side-up!
    silk_texts = [
        ("PRI (BOT)",     4.50,  3.20,   0,  "F.SilkS", 0.85, 0.16),
        ("1:1 12T",      16.80, 27.20,   0,  "F.SilkS", 0.82, 0.16),
        ("EE22 PC95",     4.50, 24.80,   0,  "F.SilkS", 0.82, 0.16),
        ("SEC (TOP)",     4.50, 24.80, 180,  "B.SilkS", 0.85, 0.16),
        ("1:1 12T",      16.80,  0.80, 180,  "B.SilkS", 0.82, 0.16),
        ("EE22 PC95",     4.50,  3.20, 180,  "B.SilkS", 0.82, 0.16),
    ]
    for i, (txt, tx, ty, rot, lyr, sz, th) in enumerate(silk_texts):
        mirror = " (justify mirror)" if lyr.startswith("B.") else ""
        lines.append(f'\t(gr_text "{txt}" (at {tx:.4f} {ty:.4f} {rot}) (layer "{lyr}") (uuid "{det_uuid(f"silk_{i}")}") (effects (font (size {sz} {sz}) (thickness {th})){mirror}))')

    # Explicit Fabrication Note on Cmts.User
    lines.append(f'\t(gr_text "FAB NOTE: 2-Layer 0.80mm FR-4, 1oz Cu. Milled EE22/08/13 slots clear up to D=2.0mm CNC bit. Tent 0.40mm via. Order >=6 pcs (2 boards/ch)." (at {BOARD_W/2:.4f} -2.2000 0) (layer "Cmts.User") (uuid "{det_uuid("fab_note")}") (effects (font (size 0.85 0.85) (thickness 0.15))))')

    # Rugged inner join via (0.80 mm pad / 0.40 mm drill = 0.20 mm annular ring, intact on BOTH F.Cu & B.Cu, tented!)
    lines.append(f'\t(via (at {XC_CORE+V_JOIN[0]:.4f} {YC+V_JOIN[1]:.4f}) (size 0.80) (drill 0.40) (layers "F.Cu" "B.Cu") (remove_unused_layers no) (keep_end_layers yes) (net 1) (uuid "{det_uuid("via_join")}"))')

    def add_segs(segs, width, layer, net_id, prefix):
        for idx, (a, b) in enumerate(segs):
            lines.append(
                f'\t(segment (start {XC_CORE+a[0]:.4f} {YC+a[1]:.4f}) (end {XC_CORE+b[0]:.4f} {YC+b[1]:.4f}) '
                f'(width {width:.4f}) (layer "{layer}") (net {net_id}) (uuid "{det_uuid(f"{prefix}_{idx}")}"))'
            )

    add_segs(l1_segs, W, "F.Cu", 1, "l1")
    add_segs(l2_segs, W, "B.Cu", 1, "l2")

    for idx, (a, b, w, lyr, nid) in enumerate(lead_segs):
        lines.append(
            f'\t(segment (start {XC_CORE+a[0]:.4f} {YC+a[1]:.4f}) (end {XC_CORE+b[0]:.4f} {YC+b[1]:.4f}) '
            f'(width {w:.4f}) (layer "{lyr}") (net {nid}) (uuid "{det_uuid(f"lead_{idx}")}"))'
        )

    lines.append(")\n")
    with open(os.path.join(OUT_DIR, "planar_transformer_ee22_2l.kicad_pcb"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, "reports"), exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, "gerbers"), exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, "renders"), exist_ok=True)
    os.makedirs(os.path.join(OUT_DIR, "sim"), exist_ok=True)
    write_fp_sym_tables()
    write_symbol_lib()
    write_footprints()
    write_dru()
    write_kicad_pro()
    write_schematic()
    write_pcb()
    print(f"\nGenerated Rev 1.0 EE22/08/13 2-Layer KiCad 10 project in: {OUT_DIR}")

if __name__ == "__main__":
    main()
