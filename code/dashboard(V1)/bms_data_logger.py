#!/usr/bin/env python3
"""
BMS Data Logger & Plotting Utility
----------------------------------
Logs real-time battery telemetry data from the Arduino BMS (or a high-fidelity simulator)
to a CSV file with timestamps, parses the fields, and plots charging and discharging curves.

Usage:
  1. Log data from a serial port:
     python bms_data_logger.py --mode log --port COM3 --output bms_log.csv
  2. Run simulation logging (generates standard charge/discharge data):
     python bms_data_logger.py --mode log --sim --duration 120 --output bms_log.csv
  3. Plot curves from logged data:
     python bms_data_logger.py --mode plot --input bms_log.csv --output-dir plots
"""

import os
import sys
import re
import time
import csv
import argparse
import random
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# Regular expression to parse key-value pairs from BMS telemetry
# Matches keys like 'state', 'V_in', 'C1', 'current bleed[0]' followed by a colon and the value
BMS_KEY_VALUE_PATTERN = re.compile(r"([\w\s\[\]_]+):[:\s]*([-+]?\d*\.\d+|\d+|[a-zA-Z_]+)[VA%]*")

class BMSLogSimulator:
    """
    Simulates a high-fidelity charging and discharging cycle of a 3-cell battery pack
    to produce realistic strings matching the display() output of bms_2.ino.
    """
    def __init__(self, total_steps=120):
        self.total_steps = total_steps
        self.current_step = 0
        self.soc = 100.0  # Start fully charged for discharging first
        self.state = "DISCHARGE"  # Start by discharging, then charge
        self.cells_soc = [100.0, 99.5, 99.0] # slight imbalance
        self.cell_irs = [0.091, 0.112, 0.131] # Ohms (from bms_2.ino fresh_ir)
        self.soh = [99.0, 98.2, 99.5]
        self.health_labels = ["GOOD", "GOOD", "GOOD"]
        
        # OCV-SOC lookup points (realistic battery chemistry)
        self.soc_pts = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0]
        self.ocv_pts = [3.0, 3.25, 3.4, 3.55, 3.65, 3.73, 3.82, 3.9, 4.0, 4.05, 4.2]

    def get_ocv(self, soc_val):
        fraction = soc_val / 100.0
        fraction = max(0.0, min(1.0, fraction))
        return np.interp(fraction, self.soc_pts, self.ocv_pts)

    def step(self):
        self.current_step += 1
        half = self.total_steps // 2
        
        # Transition states at halfway point
        if self.current_step > half:
            self.state = "CHARGE"
        else:
            self.state = "DISCHARGE"
            
        if self.state == "DISCHARGE":
            # Simulate discharging (SERIES mode)
            # Linearly drop SOC from 100 to 5
            target_soc = 100.0 - (self.current_step / half) * 95.0
            self.soc = max(5.0, target_soc)
            for i in range(3):
                self.cells_soc[i] = max(4.0, self.soc - i * 0.5)
                
            current = -1.50  # 1.5A discharge load
            charging = 0
            load_state = 1
            config_mode = "SERIES"
            v_in = 0.0
            dac = 4095
            true_charge_current = 0.0
            bleed = [0.0, 0.0, 0.0]
        else:
            # Simulate charging (SERIES mode as configured in bms_2.ino)
            # Linearly increase SOC from 5 to 100
            charge_progress = (self.current_step - half) / half
            self.soc = min(100.0, 5.0 + charge_progress * 95.0)
            for i in range(3):
                self.cells_soc[i] = min(100.0, self.soc - (2 - i) * 0.3)
                
            # CC-CV charging profile
            if self.soc < 85.0:
                current = 2.80  # CC Mode (MAX_CURRENT = 1.4*2 = 2.8A)
                dac = int(4095 - (current * 400))
            else:
                # Decay current in CV Mode
                current = max(0.3, 2.80 * (1.0 - (self.soc - 85.0) / 15.0))
                dac = int(current * 900)
                
            charging = 1
            load_state = 0
            config_mode = "SERIES"
            v_in = 13.5  # Charger active
            true_charge_current = max(0.0, current - 0.05)
            
            # Balancing active if any cell > 3.9V
            bleed = [0.0, 0.0, 0.0]
            for i in range(3):
                v_cell = self.get_ocv(self.cells_soc[i]) + current * self.cell_irs[i]
                if v_cell > 3.9 and i != 2:  # Assume cell 3 is slowest, balance 1 & 2
                    bleed[i] = round(v_cell / 10.0, 2)
        
        # Calculate cell voltages (OCV + IR drop)
        cell_voltages = []
        for i in range(3):
            ocv = self.get_ocv(self.cells_soc[i])
            ir_drop = current * self.cell_irs[i]
            v_term = ocv + ir_drop
            cell_voltages.append(max(2.8, min(4.25, v_term)))
            
        v_bat = sum(cell_voltages)  # SERIES configuration sum
        
        # Slowly degrade SOH
        for i in range(3):
            self.soh[i] = max(0.0, self.soh[i] - 0.005)
            
        # Format the telemetry line exactly like display() in bms_2.ino
        bms_str = (
            f"state: {config_mode} V_in:{v_in:.2f}V V_bat:{v_bat:.2f}V "
            f"C1:{cell_voltages[0]:.2f}V C2:{cell_voltages[1]:.2f}V C3:{cell_voltages[2]:.2f}V "
            f"I:{current:.2f}A I_bat:{true_charge_current:.2f}A SOC:{self.soc:.2f}% "
            f"SOH1:{self.soh[0]:.2f}% H1:{self.health_labels[0]} "
            f"SOH2:{self.soh[1]:.2f}% H2:{self.health_labels[1]} "
            f"SOH3:{self.soh[2]:.2f}% H3:{self.health_labels[2]} "
            f"cycles:0.12 dac:{dac} "
            f"current bleed[0]: {bleed[0]:.2f} current bleed[1]: {bleed[1]:.2f} current bleed[2]: {bleed[2]:.2f} "
            f"charging: {charging} load: {load_state}"
        )
        return bms_str

def parse_bms_line(line):
    """
    Parses a BMS display() line and extracts key-value pairs.
    Normalizes keys (replacing spaces/brackets with underscores).
    """
    data = {}
    # Use key list matching display() output for exact extraction
    keys = [
        "state", "V_in", "V_bat", "C1", "C2", "C3", "I", "I_bat", "SOC", 
        "SOH1", "H1", "SOH2", "H2", "SOH3", "H3", "cycles", "dac", 
        "current bleed[0]", "current bleed[1]", "current bleed[2]", "charging", "load"
    ]
    
    for key in keys:
        # Match key: followed by optional spaces and values (numbers or words)
        pattern = re.compile(rf"{re.escape(key)}:\s*([-+]?\d*\.\d+|\d+|[a-zA-Z_]+)")
        match = pattern.search(line)
        if match:
            val = match.group(1)
            # Normalize key name for CSV headers
            norm_key = key.replace(" ", "_").replace("[", "_").replace("]", "_")
            try:
                data[norm_key] = float(val)
            except ValueError:
                data[norm_key] = val
    return data

def log_data(port, baudrate, output_file, use_sim, duration):
    """
    Connects to the BMS (or simulator) and records the data to a CSV file.
    """
    print(f"BMS Data Logger started. Output file: {output_file}")
    
    # Define CSV Headers
    headers = [
        "Timestamp", "state", "V_in", "V_bat", "C1", "C2", "C3", "I", "I_bat", "SOC",
        "SOH1", "H1", "SOH2", "H2", "SOH3", "H3", "cycles", "dac",
        "current_bleed_0_", "current_bleed_1_", "current_bleed_2_", "charging", "load"
    ]
    
    # Initialize output directory
    dir_name = os.path.dirname(output_file)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name)
        
    # Open CSV and write headers if new file
    file_exists = os.path.exists(output_file)
    try:
        csv_file = open(output_file, mode='a', newline='')
        writer = csv.writer(csv_file)
        if not file_exists:
            writer.writerow(headers)
            csv_file.flush()
    except Exception as e:
        print(f"Error opening CSV file {output_file}: {e}")
        return

    serial_conn = None
    sim = None
    
    if use_sim:
        print("Running in Simulation Mode...")
        sim = BMSLogSimulator(total_steps=duration if duration else 120)
    else:
        import serial
        print(f"Connecting to Serial Port {port} at {baudrate} baud...")
        try:
            serial_conn = serial.Serial(port, baudrate, timeout=1.0)
            serial_conn.reset_input_buffer()
            print("Connected successfully! Logging data (Press Ctrl+C to stop)...")
        except Exception as e:
            print(f"Failed to connect to serial port {port}: {e}")
            print("Switching to Simulation Mode as fallback...")
            use_sim = True
            sim = BMSLogSimulator(total_steps=duration if duration else 120)

    start_time = time.time()
    count = 0
    
    try:
        while True:
            # Check duration limits
            if duration and (time.time() - start_time) >= duration and not use_sim:
                print(f"Reached specified duration of {duration} seconds. Stopping...")
                break
            if use_sim and sim.current_step >= sim.total_steps:
                print("Simulation completed.")
                break
                
            raw_line = ""
            if use_sim:
                raw_line = sim.step()
                time.sleep(0.5)  # simulate delay between outputs
            else:
                if serial_conn.in_waiting > 0:
                    raw_bytes = serial_conn.readline()
                    raw_line = raw_bytes.decode('utf-8', errors='ignore').strip()
            
            if raw_line:
                print(f"[REC]: {raw_line}")
                parsed_data = parse_bms_line(raw_line)
                
                if parsed_data:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    row = [timestamp]
                    for col in headers[1:]:
                        row.append(parsed_data.get(col, ""))
                        
                    writer.writerow(row)
                    csv_file.flush()
                    count += 1
                    
    except KeyboardInterrupt:
        print("\nLogging interrupted by user.")
    finally:
        csv_file.close()
        if serial_conn and serial_conn.is_open:
            serial_conn.close()
        print(f"Logging session closed. Logged {count} data rows to {output_file}.")

def plot_curves(input_file, output_dir):
    """
    Reads the logged BMS CSV telemetry file and plots the charging/discharging curves.
    """
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} does not exist.")
        return
        
    print(f"Reading data from {input_file}...")
    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return
        
    if len(df) < 2:
        print("Error: Not enough data points to plot.")
        return

    # Check output directory
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"Total data points: {len(df)}")
    
    # Parse timestamp as datetime, coercing invalid values to NaT
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df.dropna(subset=['Timestamp']).copy()
    
    if len(df) < 2:
        print("Error: Not enough valid data points to plot after filtering.")
        return

    # Force numerical columns to float, converting any string errors/empty spaces to NaN
    cols_to_numeric = ['V_in', 'V_bat', 'C1', 'C2', 'C3', 'I', 'I_bat', 'SOC', 'cycles', 'dac', 'charging', 'load']
    for col in cols_to_numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Filter out current outliers (> 15A or < -15A) in-memory only (do not store back to CSV)
    if 'I' in df.columns:
        df.loc[df['I'].abs() > 15.0, 'I'] = np.nan
        df['I'] = df['I'].ffill().bfill()
    if 'I_bat' in df.columns:
        df.loc[df['I_bat'].abs() > 15.0, 'I_bat'] = np.nan
        df['I_bat'] = df['I_bat'].ffill().bfill()

    # Add elapsed time in seconds from start
    start_time = df['Timestamp'].iloc[0]
    df['Elapsed_Time_s'] = (df['Timestamp'] - start_time).dt.total_seconds()
    
    # Setup premium dark styling for plotting
    plt.style.use('dark_background')
    
    # ----------------------------------------------------
    # 1. Overall Telemetry Dashboard
    # ----------------------------------------------------
    print("Generating Overall Telemetry Dashboard...")
    fig1 = plt.figure(1, figsize=(12, 8))
    fig1.canvas.manager.set_window_title("BMS Overall Telemetry")
    
    # 2 subplots: Voltage (top), Current (bottom)
    ax_vol = plt.subplot(2, 1, 1)
    ax_cur = plt.subplot(2, 1, 2, sharex=ax_vol)
    
    # Plot Voltages (V_bat and Cells)
    ax_vol.plot(df['Elapsed_Time_s'], df['V_bat'], label='Pack Voltage (V_bat)', color='#FFEB3B', linewidth=2.5)
    ax_vol.plot(df['Elapsed_Time_s'], df['C1'], label='Cell 1 (C1)', color='#42A5F5', linestyle='--', alpha=0.8)
    ax_vol.plot(df['Elapsed_Time_s'], df['C2'], label='Cell 2 (C2)', color='#26A69A', linestyle='--', alpha=0.8)
    ax_vol.plot(df['Elapsed_Time_s'], df['C3'], label='Cell 3 (C3)', color='#AB47BC', linestyle='--', alpha=0.8)
    ax_vol.set_ylabel('Voltage (V)', color='#E0E0E0', fontsize=11)
    ax_vol.grid(True, color='#444444', linestyle=':', alpha=0.6)
    ax_vol.legend(loc='upper right', framealpha=0.3)
    ax_vol.set_title('BMS Telemetry History - Voltage and Current', fontsize=14, color='#FFFFFF', fontweight='bold', pad=15)
    
    # Plot Current
    ax_cur.plot(df['Elapsed_Time_s'], df['I'], label='Current (I)', color='#E0E0E0', linewidth=2)
    ax_cur.fill_between(df['Elapsed_Time_s'], 0, df['I'], where=(df['I'] > 0.05), color='#00E676', alpha=0.3, label='Charging')
    ax_cur.fill_between(df['Elapsed_Time_s'], 0, df['I'], where=(df['I'] < -0.05), color='#FF1744', alpha=0.3, label='Discharging')
    ax_cur.axhline(0, color='#757575', linestyle='-', linewidth=0.8)
    ax_cur.set_ylabel('Current (A)', color='#E0E0E0', fontsize=11)
    ax_cur.set_xlabel('Elapsed Time (seconds)', color='#E0E0E0', fontsize=11)
    ax_cur.grid(True, color='#444444', linestyle=':', alpha=0.6)
    ax_cur.legend(loc='upper right', framealpha=0.3)
    
    plt.tight_layout()
    overall_plot_path = os.path.join(output_dir, 'bms_overall_telemetry.png')
    plt.savefig(overall_plot_path, dpi=150)
    print(f"Saved: {overall_plot_path}")
    
    # ----------------------------------------------------
    # 2. Charging Curve (Filter rows where charging == 1 or I > 0.05)
    # ----------------------------------------------------
    charging_df = df[(df['charging'] == 1) | (df['I'] > 0.05)].copy()
    if not charging_df.empty:
        print("Generating Charging Curves...")
        charging_df['Charge_Time_s'] = charging_df['Elapsed_Time_s'] - charging_df['Elapsed_Time_s'].iloc[0]
        
        fig2 = plt.figure(2, figsize=(10, 8))
        fig2.canvas.manager.set_window_title("BMS Charging Profile")
        
        ax1 = plt.subplot(2, 1, 1)
        ax2 = plt.subplot(2, 1, 2, sharex=ax1)
        
        # Plot Voltages vs Charging Time
        ax1.plot(charging_df['Charge_Time_s'], charging_df['V_bat'], label='Pack Voltage (V_bat)', color='#00E676', linewidth=2.5)
        ax1.plot(charging_df['Charge_Time_s'], charging_df['C1'], label='Cell 1 (C1)', color='#42A5F5', alpha=0.8)
        ax1.plot(charging_df['Charge_Time_s'], charging_df['C2'], label='Cell 2 (C2)', color='#26A69A', alpha=0.8)
        ax1.plot(charging_df['Charge_Time_s'], charging_df['C3'], label='Cell 3 (C3)', color='#AB47BC', alpha=0.8)
        ax1.set_ylabel('Voltage (V)', color='#E0E0E0', fontsize=11)
        ax1.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax1.legend(loc='lower right', framealpha=0.3)
        ax1.set_title('BMS Battery Charging Curve (CC-CV Phase)', fontsize=14, color='#00E676', fontweight='bold', pad=15)
        
        # Plot Current vs Charging Time
        ax2.plot(charging_df['Charge_Time_s'], charging_df['I'], label='Charge Current (A)', color='#FF9800', linewidth=2)
        ax2.set_ylabel('Current (A)', color='#FF9800', fontsize=11)
        ax2.tick_params(axis='y', labelcolor='#FF9800')
        ax2.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax2.legend(loc='upper right', framealpha=0.3)
        ax2.set_xlabel('Charging Time (seconds)', color='#E0E0E0', fontsize=11)
        
        plt.tight_layout()
        charge_plot_path = os.path.join(output_dir, 'bms_charging_curve.png')
        plt.savefig(charge_plot_path, dpi=150)
        print(f"Saved: {charge_plot_path}")
    else:
        print("Warning: No charging data found in log. Skipping charging plot.")
        
    # ----------------------------------------------------
    # 3. Discharging Curve (Filter rows where load == 1 or I < -0.05)
    # ----------------------------------------------------
    discharging_df = df[(df['load'] == 1) | (df['I'] < -0.05)].copy()
    if not discharging_df.empty:
        print("Generating Discharging Curves...")
        discharging_df['Discharge_Time_s'] = discharging_df['Elapsed_Time_s'] - discharging_df['Elapsed_Time_s'].iloc[0]
        
        fig3 = plt.figure(3, figsize=(10, 8))
        fig3.canvas.manager.set_window_title("BMS Discharging Profile")
        
        ax1 = plt.subplot(2, 1, 1)
        ax2 = plt.subplot(2, 1, 2, sharex=ax1)
        
        # Plot Voltages vs Discharging Time
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['V_bat'], label='Pack Voltage (V_bat)', color='#FF1744', linewidth=2.5)
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['C1'], label='Cell 1 (C1)', color='#42A5F5', alpha=0.8)
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['C2'], label='Cell 2 (C2)', color='#26A69A', alpha=0.8)
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['C3'], label='Cell 3 (C3)', color='#AB47BC', alpha=0.8)
        ax1.set_ylabel('Voltage (V)', color='#E0E0E0', fontsize=11)
        ax1.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax1.legend(loc='upper right', framealpha=0.3)
        ax1.set_title('BMS Battery Discharging Curve (Load Profile)', fontsize=14, color='#FF1744', fontweight='bold', pad=15)
        
        # Plot Current vs Discharging Time
        ax2.plot(discharging_df['Discharge_Time_s'], discharging_df['I'], label='Discharge Current (A)', color='#FF5722', linewidth=2)
        ax2.set_ylabel('Current (A)', color='#FF5722', fontsize=11)
        ax2.tick_params(axis='y', labelcolor='#FF5722')
        ax2.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax2.legend(loc='upper right', framealpha=0.3)
        ax2.set_xlabel('Discharging Time (seconds)', color='#E0E0E0', fontsize=11)
        
        plt.tight_layout()
        discharge_plot_path = os.path.join(output_dir, 'bms_discharging_curve.png')
        plt.savefig(discharge_plot_path, dpi=150)
        print(f"Saved: {discharge_plot_path}")
    else:
        print("Warning: No discharging data found in log. Skipping discharging plot.")
        
    print("All plots generated and saved successfully!")
    
    # Open the Matplotlib interactive viewer for all plots
    print("Opening interactive plots window...")
    plt.show()

def main():
    parser = argparse.ArgumentParser(description="BMS Logging and Plotting Tool")
    parser.add_argument("--mode", choices=["log", "plot"], required=True, help="Run mode: 'log' to log telemetry, 'plot' to visualize.")
    parser.add_argument("--port", default="COM3", help="BMS Serial Port (default: COM3)")
    parser.add_argument("--baud", type=int, default=115200, help="BMS Serial Baudrate (default: 115200)")
    parser.add_argument("--output", default="bms_telemetry_log.csv", help="Output CSV path (default: bms_telemetry_log.csv)")
    parser.add_argument("--input", default="bms_telemetry_log.csv", help="Input CSV path for plotting (default: bms_telemetry_log.csv)")
    parser.add_argument("--output-dir", default="plots", help="Directory to save generated charts (default: plots)")
    parser.add_argument("--sim", action="store_true", help="Force Simulation/Demo Mode (no serial hardware required)")
    parser.add_argument("--duration", type=int, default=0, help="Logging duration in seconds (default is unlimited for serial, 120s for simulation)")
    
    args = parser.parse_args()
    
    if args.mode == "log":
        log_data(args.port, args.baud, args.output, args.sim, args.duration)
    elif args.mode == "plot":
        plot_curves(args.input, args.output_dir)

if __name__ == "__main__":
    main()
