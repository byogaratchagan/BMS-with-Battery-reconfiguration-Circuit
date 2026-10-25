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
    was_charging = False
    was_discharging = False
    first_line = True
    logging_active = False
    
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
                    is_charging = parsed_data.get("charging", 0.0)
                    is_discharging = parsed_data.get("load", 0.0)
                    
                    if first_line:
                        was_charging = (is_charging == 1.0)
                        was_discharging = (is_discharging == 1.0)
                        first_line = False
                        
                    charge_just_started = (is_charging == 1.0 and not was_charging)
                    discharge_just_completed = (is_discharging == 0.0 and was_discharging)
                    
                    was_charging = (is_charging == 1.0)
                    was_discharging = (is_discharging == 1.0)
                    
                    if not logging_active:
                        if discharge_just_completed or charge_just_started:
                            logging_active = True
                            print("\n" + "="*40)
                            print("   STARTING LOGGING (Trigger Condition Met)")
                            print("="*40)
                    else:
                        if discharge_just_completed:
                            # Log this final line before breaking
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            row = [timestamp]
                            for col in headers[1:]:
                                row.append(parsed_data.get(col, ""))
                            writer.writerow(row)
                            csv_file.flush()
                            count += 1
                            
                            print("\n" + "="*40)
                            print("   FULL CYCLE FINISHED ALARM (Discharge Completed)")
                            print("="*40)
                            print("Stopping serial communication and ending data logging...")
                            try:
                                import winsound
                                for _ in range(5):
                                    winsound.Beep(2500, 300)
                                    time.sleep(0.1)
                            except ImportError:
                                print('\a'*5)
                            break
                            
                    if logging_active:
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

def plot_curves(input_file, output_dir, ac_meter_wh=0.0, prefix="", show_plots=True):
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

    # Sort by Timestamp to ensure chronological order
    df = df.sort_values(by='Timestamp').reset_index(drop=True)

    # Add elapsed time in seconds from start
    start_time = df['Timestamp'].iloc[0]
    df['Elapsed_Time_s'] = (df['Timestamp'] - start_time).dt.total_seconds()
    
    if 'V_bat' in df.columns and 'I' in df.columns:
        df['Power_W'] = df['V_bat'] * df['I']
    
    # Calculate time differences between consecutive steps (dt in seconds), cap at 5s to ignore massive connection gaps
    df['dt'] = df['Elapsed_Time_s'].diff().fillna(0).clip(upper=5.0)
    
    # Calculate energy step in Watt-hours: Power (W) * dt (s) / 3600
    if 'Power_W' in df.columns:
        power_clean = df['Power_W'].fillna(0)
        df['Energy_Step_Wh'] = (power_clean * df['dt']) / 3600.0
        # Cumulative Energy Charged (Consumed: positive power)
        df['Cum_Energy_Charged_Wh'] = df['Energy_Step_Wh'].clip(lower=0).cumsum()
        # Cumulative Energy Discharged (Spent: negative power)
        df['Cum_Energy_Discharged_Wh'] = (-df['Energy_Step_Wh']).clip(lower=0).cumsum()
    else:
        df['Cum_Energy_Charged_Wh'] = 0.0
        df['Cum_Energy_Discharged_Wh'] = 0.0

    # Setup premium dark styling for plotting
    plt.style.use('dark_background')
    
    file_title = f" [{prefix}]" if prefix else ""
    fig_title_ext = f" - {prefix}" if prefix else ""
    
    # ----------------------------------------------------
    # 1. Overall Telemetry Dashboard
    # ----------------------------------------------------
    print("Generating Overall Telemetry Dashboard...")
    fig1 = plt.figure(figsize=(12, 8))
    fig1.canvas.manager.set_window_title(f"BMS Overall Telemetry{fig_title_ext}")
    
    # 3 subplots: Voltage (top), Current (middle), Power (bottom)
    ax_vol = plt.subplot(3, 1, 1)
    ax_cur = plt.subplot(3, 1, 2, sharex=ax_vol)
    ax_pwr = plt.subplot(3, 1, 3, sharex=ax_vol)
    
    # Plot Voltages (V_bat and Cells)
    ax_vol.plot(df['Elapsed_Time_s'], df['V_bat'], label='Pack Voltage (V_bat)', color='#FFEB3B', linewidth=2.5)
    ax_vol.plot(df['Elapsed_Time_s'], df['C1'], label='Cell 1 (C1)', color='#42A5F5', linestyle='--', alpha=0.8)
    ax_vol.plot(df['Elapsed_Time_s'], df['C2'], label='Cell 2 (C2)', color='#26A69A', linestyle='--', alpha=0.8)
    ax_vol.plot(df['Elapsed_Time_s'], df['C3'], label='Cell 3 (C3)', color='#AB47BC', linestyle='--', alpha=0.8)
    ax_vol.set_ylabel('Voltage (V)', color='#E0E0E0', fontsize=11)
    ax_vol.grid(True, color='#444444', linestyle=':', alpha=0.6)
    ax_vol.legend(loc='upper right', framealpha=0.3)
    ax_vol.set_title(f'BMS Telemetry History{file_title} - Voltage, Current, and Power', fontsize=14, color='#FFFFFF', fontweight='bold', pad=15)
    
    # Plot Current
    ax_cur.plot(df['Elapsed_Time_s'], df['I'], label='Current (I)', color='#E0E0E0', linewidth=2)
    ax_cur.fill_between(df['Elapsed_Time_s'], 0, df['I'], where=(df['I'] > 0.05), color='#00E676', alpha=0.3, label='Charging')
    ax_cur.fill_between(df['Elapsed_Time_s'], 0, df['I'], where=(df['I'] < -0.05), color='#FF1744', alpha=0.3, label='Discharging')
    ax_cur.axhline(0, color='#757575', linestyle='-', linewidth=0.8)
    ax_cur.set_ylabel('Current (A)', color='#E0E0E0', fontsize=11)
    ax_cur.grid(True, color='#444444', linestyle=':', alpha=0.6)
    ax_cur.legend(loc='upper right', framealpha=0.3)
    
    # Plot Power
    if 'Power_W' in df.columns:
        ax_pwr.plot(df['Elapsed_Time_s'], df['Power_W'], label='Power (W)', color='#BA68C8', linewidth=2)
        ax_pwr.fill_between(df['Elapsed_Time_s'], 0, df['Power_W'], where=(df['Power_W'] > 0), color='#00E676', alpha=0.2, label='Charge Power')
        ax_pwr.fill_between(df['Elapsed_Time_s'], 0, df['Power_W'], where=(df['Power_W'] < 0), color='#FF1744', alpha=0.2, label='Discharge Power')
        ax_pwr.axhline(0, color='#757575', linestyle='-', linewidth=0.8)
        ax_pwr.set_ylabel('Power (W)', color='#E0E0E0', fontsize=11)
        ax_pwr.set_xlabel('Elapsed Time (seconds)', color='#E0E0E0', fontsize=11)
        ax_pwr.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax_pwr.legend(loc='upper right', framealpha=0.3)
    
    plt.tight_layout()
    file_prefix = f"{prefix}_" if prefix else ""
    overall_plot_path = os.path.join(output_dir, f'{file_prefix}bms_overall_telemetry.png')
    plt.savefig(overall_plot_path, dpi=150)
    print(f"Saved: {overall_plot_path}")
    
    # ----------------------------------------------------
    # 2. Charging Curve (Filter rows where charging == 1 or I > 0.05)
    # ----------------------------------------------------
    charging_df = df[(df['charging'] == 1) | (df['I'] > 0.05)].copy()
    if not charging_df.empty:
        print("Generating Charging Curves...")
        charging_df['Charge_Time_s'] = charging_df['Elapsed_Time_s'] - charging_df['Elapsed_Time_s'].iloc[0]
        
        # Calculate cumulative charge energy for this charging session
        if 'Energy_Step_Wh' in charging_df.columns:
            charging_df['Charge_Energy_Step_Wh'] = charging_df['Energy_Step_Wh']
            charging_df['Cum_Charge_Energy_Wh'] = charging_df['Charge_Energy_Step_Wh'].clip(lower=0).cumsum()
            total_wh = charging_df['Cum_Charge_Energy_Wh'].iloc[-1] if not charging_df.empty else 0.0
            
            print(f"\n[{'='*40}]")
            print(f"  TOTAL ENERGY CONSUMED (CHARGE): {total_wh:.3f} Wh")
            print(f"[{'='*40}]\n")
        else:
            charging_df['Cum_Charge_Energy_Wh'] = 0.0
        
        fig2 = plt.figure(figsize=(10, 10))
        fig2.canvas.manager.set_window_title(f"BMS Charging Profile{fig_title_ext}")
        
        ax1 = plt.subplot(4, 1, 1)
        ax2 = plt.subplot(4, 1, 2, sharex=ax1)
        ax3 = plt.subplot(4, 1, 3, sharex=ax1)
        ax4 = plt.subplot(4, 1, 4, sharex=ax1)
        
        # Plot Voltages vs Charging Time
        ax1.plot(charging_df['Charge_Time_s'], charging_df['V_bat'], label='Pack Voltage (V_bat)', color='#00E676', linewidth=2.5)
        ax1.plot(charging_df['Charge_Time_s'], charging_df['C1'], label='Cell 1 (C1)', color='#42A5F5', alpha=0.8)
        ax1.plot(charging_df['Charge_Time_s'], charging_df['C2'], label='Cell 2 (C2)', color='#26A69A', alpha=0.8)
        ax1.plot(charging_df['Charge_Time_s'], charging_df['C3'], label='Cell 3 (C3)', color='#AB47BC', alpha=0.8)
        ax1.set_ylabel('Voltage (V)', color='#E0E0E0', fontsize=11)
        ax1.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax1.legend(loc='lower right', framealpha=0.3)
        ax1.set_title(f'BMS Battery Charging Curve{file_title} (CC-CV Phase)', fontsize=14, color='#00E676', fontweight='bold', pad=15)
        
        # Plot Current vs Charging Time
        ax2.plot(charging_df['Charge_Time_s'], charging_df['I'], label='Charge Current (A)', color='#FF9800', linewidth=2)
        ax2.set_ylabel('Current (A)', color='#FF9800', fontsize=11)
        ax2.tick_params(axis='y', labelcolor='#FF9800')
        ax2.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax2.legend(loc='upper right', framealpha=0.3)
        
        # Plot Power vs Charging Time
        if 'Power_W' in charging_df.columns:
            ax3.plot(charging_df['Charge_Time_s'], charging_df['Power_W'], label='Charge Power (W)', color='#E91E63', linewidth=2)
            ax3.set_ylabel('Power (W)', color='#E91E63', fontsize=11)
            ax3.tick_params(axis='y', labelcolor='#E91E63')
            ax3.grid(True, color='#444444', linestyle=':', alpha=0.6)
            ax3.legend(loc='upper right', framealpha=0.3)
        
        # Plot Cumulative Energy Charged vs Charging Time
        charge_label = 'Cumulative Energy Charged (Wh)'
        ax4.plot(charging_df['Charge_Time_s'], charging_df['Cum_Charge_Energy_Wh'], label=charge_label, color='#00E5FF', linewidth=2.5)
        ax4.fill_between(charging_df['Charge_Time_s'], 0, charging_df['Cum_Charge_Energy_Wh'], color='#00E5FF', alpha=0.15)
        ax4.set_ylabel('Energy (Wh)', color='#00E5FF', fontsize=11)
        ax4.tick_params(axis='y', labelcolor='#00E5FF')
        ax4.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax4.legend(loc='upper left', framealpha=0.3)
        ax4.set_xlabel('Charging Time (seconds)', color='#E0E0E0', fontsize=11)
        
        plt.tight_layout()
        charge_plot_path = os.path.join(output_dir, f'{file_prefix}bms_charging_curve.png')
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
        
        # Calculate cumulative discharge energy for this discharging session
        if 'Energy_Step_Wh' in discharging_df.columns:
            # Power is negative during discharge, so take negative to get positive energy spent
            discharging_df['Discharge_Energy_Step_Wh'] = -discharging_df['Energy_Step_Wh']
            discharging_df['Cum_Discharge_Energy_Wh'] = discharging_df['Discharge_Energy_Step_Wh'].clip(lower=0).cumsum()
        else:
            discharging_df['Cum_Discharge_Energy_Wh'] = 0.0
            
        fig3 = plt.figure(figsize=(10, 10))
        fig3.canvas.manager.set_window_title(f"BMS Discharging Profile{fig_title_ext}")
        
        ax1 = plt.subplot(4, 1, 1)
        ax2 = plt.subplot(4, 1, 2, sharex=ax1)
        ax3 = plt.subplot(4, 1, 3, sharex=ax1)
        ax4 = plt.subplot(4, 1, 4, sharex=ax1)
        
        # Plot Voltages vs Discharging Time
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['V_bat'], label='Pack Voltage (V_bat)', color='#FF1744', linewidth=2.5)
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['C1'], label='Cell 1 (C1)', color='#42A5F5', alpha=0.8)
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['C2'], label='Cell 2 (C2)', color='#26A69A', alpha=0.8)
        ax1.plot(discharging_df['Discharge_Time_s'], discharging_df['C3'], label='Cell 3 (C3)', color='#AB47BC', alpha=0.8)
        ax1.set_ylabel('Voltage (V)', color='#E0E0E0', fontsize=11)
        ax1.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax1.legend(loc='upper right', framealpha=0.3)
        ax1.set_title(f'BMS Battery Discharging Curve{file_title} (Load Profile)', fontsize=14, color='#FF1744', fontweight='bold', pad=15)
        
        # Plot Current vs Discharging Time
        ax2.plot(discharging_df['Discharge_Time_s'], discharging_df['I'], label='Discharge Current (A)', color='#FF5722', linewidth=2)
        ax2.set_ylabel('Current (A)', color='#FF5722', fontsize=11)
        ax2.tick_params(axis='y', labelcolor='#FF5722')
        ax2.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax2.legend(loc='upper right', framealpha=0.3)
        
        # Plot Power vs Discharging Time
        if 'Power_W' in discharging_df.columns:
            ax3.plot(discharging_df['Discharge_Time_s'], discharging_df['Power_W'], label='Discharge Power (W)', color='#9C27B0', linewidth=2)
            ax3.set_ylabel('Power (W)', color='#9C27B0', fontsize=11)
            ax3.tick_params(axis='y', labelcolor='#9C27B0')
            ax3.grid(True, color='#444444', linestyle=':', alpha=0.6)
            ax3.legend(loc='upper right', framealpha=0.3)
        
        # Plot Cumulative Energy Discharged vs Discharging Time
        total_discharge_wh = discharging_df['Cum_Discharge_Energy_Wh'].iloc[-1] if not discharging_df.empty else 0.0
        discharge_label = 'Cumulative Energy Spent (Wh)'
        if ac_meter_wh > 0.0 and total_discharge_wh > 0.0:
            eff = (total_discharge_wh / ac_meter_wh) * 100.0
            discharge_label += f' [System Efficiency: {eff:.1f}%]'
        ax4.plot(discharging_df['Discharge_Time_s'], discharging_df['Cum_Discharge_Energy_Wh'], label=discharge_label, color='#E040FB', linewidth=2.5)
        ax4.fill_between(discharging_df['Discharge_Time_s'], 0, discharging_df['Cum_Discharge_Energy_Wh'], color='#E040FB', alpha=0.15)
        ax4.set_ylabel('Energy (Wh)', color='#E040FB', fontsize=11)
        ax4.tick_params(axis='y', labelcolor='#E040FB')
        ax4.grid(True, color='#444444', linestyle=':', alpha=0.6)
        ax4.legend(loc='upper left', framealpha=0.3)
        ax4.set_xlabel('Discharging Time (seconds)', color='#E0E0E0', fontsize=11)
        
        plt.tight_layout()
        discharge_plot_path = os.path.join(output_dir, f'{file_prefix}bms_discharging_curve.png')
        plt.savefig(discharge_plot_path, dpi=150)
        print(f"Saved: {discharge_plot_path}")
    else:
        print("Warning: No discharging data found in log. Skipping discharging plot.")
        
    # ----------------------------------------------------
    # 4. Cumulative Energy Profile (Whole Session)
    # ----------------------------------------------------
    if 'Cum_Energy_Charged_Wh' in df.columns and 'Cum_Energy_Discharged_Wh' in df.columns:
        print("Generating Cumulative Energy Profile...")
        fig4 = plt.figure(figsize=(10, 6))
        fig4.canvas.manager.set_window_title(f"BMS Cumulative Energy Profile{fig_title_ext}")
        
        plt.plot(df['Elapsed_Time_s'], df['Cum_Energy_Charged_Wh'], label='Total Energy Charged (Wh)', color='#00E5FF', linewidth=2.5)
        plt.fill_between(df['Elapsed_Time_s'], 0, df['Cum_Energy_Charged_Wh'], color='#00E5FF', alpha=0.15)
        
        plt.plot(df['Elapsed_Time_s'], df['Cum_Energy_Discharged_Wh'], label='Total Energy Spent/Discharged (Wh)', color='#E040FB', linewidth=2.5)
        plt.fill_between(df['Elapsed_Time_s'], 0, df['Cum_Energy_Discharged_Wh'], color='#E040FB', alpha=0.15)
        
        plt.title(f'BMS Cumulative Energy Over Time{file_title}', fontsize=14, color='#FFFFFF', fontweight='bold', pad=15)
        plt.ylabel('Energy (Wh)', color='#E0E0E0', fontsize=11)
        plt.xlabel('Elapsed Time (seconds)', color='#E0E0E0', fontsize=11)
        plt.grid(True, color='#444444', linestyle=':', alpha=0.6)
        plt.legend(loc='upper left', framealpha=0.3)
        
        plt.tight_layout()
        energy_plot_path = os.path.join(output_dir, f'{file_prefix}bms_cumulative_energy.png')
        plt.savefig(energy_plot_path, dpi=150)
        print(f"Saved: {energy_plot_path}")
        
    print("All plots generated and saved successfully!")
    
    if show_plots:
        # Open the Matplotlib interactive viewer for all plots
        print("Opening interactive plots window...")
        plt.show()

def compare_logs(file1, file2, ac_wh1=0.0, ac_wh2=0.0, dc_wh1=0.0, dc_wh2=0.0, output_dir="plots"):
    """ Compares two BMS CSV logs and generates a Markdown report. """
    if not os.path.exists(file1) or not os.path.exists(file2):
        print("Error: One or both input files do not exist.")
        return

    def extract_totals(file_path):
        try:
            df = pd.read_csv(file_path)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
            df = df.dropna(subset=['Timestamp']).copy()
            
            # Force numeric conversion for vital columns
            for col in ['V_bat', 'I', 'charging', 'load']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    
            df = df.sort_values(by='Timestamp').reset_index(drop=True)
            start_time = df['Timestamp'].iloc[0]
            df['Elapsed_Time_s'] = (df['Timestamp'] - start_time).dt.total_seconds()
            
            if 'V_bat' in df.columns and 'I' in df.columns:
                df['Power_W'] = df['V_bat'] * df['I']
                
            df['dt'] = df['Elapsed_Time_s'].diff().fillna(0).clip(upper=5.0)
            if 'Power_W' in df.columns:
                df['Energy_Step_Wh'] = (df['Power_W'].fillna(0) * df['dt']) / 3600.0
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            return 0.0, 0.0, 0.0, 0.0
            
        charge_wh, discharge_wh = 0.0, 0.0
        charge_time_s, discharge_time_s = 0.0, 0.0
        
        if 'Energy_Step_Wh' in df.columns:
            charging_mask = (df['charging'] == 1) | (df['I'] > 0.05)
            charge_wh = df.loc[charging_mask, 'Energy_Step_Wh'].sum()
            charge_time_s = df.loc[charging_mask, 'dt'].sum()
            
            discharging_mask = (df['load'] == 1) | (df['I'] < -0.05)
            # Power is negative during discharge, so take negative to get positive Wh
            discharge_wh = -df.loc[discharging_mask, 'Energy_Step_Wh'].sum()
            discharge_time_s = df.loc[discharging_mask, 'dt'].sum()

        return charge_wh, discharge_wh, charge_time_s, discharge_time_s

    print(f"\nParsing Log 1: {file1}")
    chg1, dis1, time_c1, time_d1 = extract_totals(file1)
    print(f"Parsing Log 2: {file2}")
    chg2, dis2, time_c2, time_d2 = extract_totals(file2)

    name1 = os.path.splitext(os.path.basename(file1))[0]
    name2 = os.path.splitext(os.path.basename(file2))[0]

    def fmt_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d} ({int(seconds)}s)"

    md = f"# BMS Configuration Comparison Report\n\n"
    md += f"**{name1}** vs **{name2}**\n\n"
    
    md += "## 1. Raw Telemetry Energy & Time\n\n"
    md += f"| Metric | {name1} | {name2} | Difference |\n"
    md += f"|---|---|---|---|\n"
    md += f"| Charge Energy (Logged DC Wh) | {chg1:.3f} | {chg2:.3f} | {abs(chg1-chg2):.3f} Wh |\n"
    md += f"| Charge Time | {fmt_time(time_c1)} | {fmt_time(time_c2)} | {fmt_time(abs(time_c1-time_c2))} |\n"
    md += f"| Discharge Energy (Wh) | {dis1:.3f} | {dis2:.3f} | {abs(dis1-dis2):.3f} Wh |\n"
    md += f"| Discharge Time | {fmt_time(time_d1)} | {fmt_time(time_d2)} | {fmt_time(abs(time_d1-time_d2))} |\n\n"

    md += "### Capacity Delivered\n\n"
    if dis1 > 0 and dis2 > 0:
        if dis1 > dis2:
            pct = ((dis1 - dis2) / dis2) * 100.0
            md += f"**{name1}** delivered **{dis1-dis2:.3f} MORE Wh** during discharge than **{name2}**. ({pct:.2f}% improvement)\n\n"
        elif dis2 > dis1:
            pct = ((dis2 - dis1) / dis1) * 100.0
            md += f"**{name2}** delivered **{dis2-dis1:.3f} MORE Wh** during discharge than **{name1}**. ({pct:.2f}% improvement)\n\n"

    def gen_savings_report(meter1, meter2, label):
        if meter1 <= 0 or meter2 <= 0:
            return f"## {label} Analysis\n\n*No meter readings provided for {label}. Skipping section.*\n\n"
            
        r = f"## {label} Analysis\n\n"
        if dis1 > 0 and dis2 > 0:
            cost1 = meter1 / dis1
            cost2 = meter2 / dis2
            baseline_dis = max(dis1, dis2)
            proj_c1 = cost1 * baseline_dis
            proj_c2 = cost2 * baseline_dis
            
            r += f"### Normalized Energy Savings (Normalized to {baseline_dis:.3f} Wh delivered capacity)\n\n"
            r += f"- To deliver {baseline_dis:.3f} Wh, **{name1}** requires: **{proj_c1:.3f} Wh** ({label})\n"
            r += f"- To deliver {baseline_dis:.3f} Wh, **{name2}** requires: **{proj_c2:.3f} Wh** ({label})\n\n"
            
            if proj_c1 > proj_c2:
                pct = ((proj_c1 - proj_c2) / proj_c1) * 100.0
                r += f"**🏆 CONCLUSION:** **{name2}** saves **{proj_c1-proj_c2:.3f} Wh ({pct:.2f}%)** compared to **{name1}**.\n\n"
            elif proj_c2 > proj_c1:
                pct = ((proj_c2 - proj_c1) / proj_c2) * 100.0
                r += f"**🏆 CONCLUSION:** **{name1}** saves **{proj_c2-proj_c1:.3f} Wh ({pct:.2f}%)** compared to **{name2}**.\n\n"
                
            eff1 = (dis1 / meter1) * 100.0
            eff2 = (dis2 / meter2) * 100.0
            r += f"### Overall System Efficiency\n\n"
            r += f"- **{name1}** Efficiency: **{eff1:.2f}%**\n"
            r += f"- **{name2}** Efficiency: **{eff2:.2f}%**\n\n"
            
            if eff1 > eff2:
                pct = ((eff1 - eff2) / eff2) * 100.0
                r += f"**🏆 WINNER:** **{name1}** is **{eff1 - eff2:.2f}%** MORE efficient than **{name2}**! ({pct:.2f}% relative improvement)\n\n"
            elif eff2 > eff1:
                pct = ((eff2 - eff1) / eff1) * 100.0
                r += f"**🏆 WINNER:** **{name2}** is **{eff2 - eff1:.2f}%** MORE efficient than **{name1}**! ({pct:.2f}% relative improvement)\n\n"
        else:
            r += f"### Un-normalized Charging Cost\n\n"
            if meter1 > meter2:
                pct = ((meter1 - meter2) / meter1) * 100.0
                r += f"**CONCLUSION (Un-normalized):** **{name2}** used **{meter1-meter2:.3f} LESS Wh** to charge than **{name1}**. (Saved {pct:.2f}% energy)\n\n"
            elif meter2 > meter1:
                pct = ((meter2 - meter1) / meter2) * 100.0
                r += f"**CONCLUSION (Un-normalized):** **{name1}** used **{meter2-meter1:.3f} LESS Wh** to charge than **{name2}**. (Saved {pct:.2f}% energy)\n\n"
        return r

    md += gen_savings_report(dc_wh1, dc_wh2, "DC Charger Meter")
    md += gen_savings_report(ac_wh1, ac_wh2, "AC Wall Meter")
    
    print("\n" + "="*60)
    print(md)
    print("="*60 + "\n")
    
    os.makedirs(output_dir, exist_ok=True)
    md_path = os.path.join(output_dir, f"comparison_report_{name1}_vs_{name2}.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"✅ Markdown report saved to: {md_path}\n")

def main():
    parser = argparse.ArgumentParser(description="BMS Logging and Plotting Tool")
    parser.add_argument("--mode", choices=["log", "plot", "compare"], required=True, help="Run mode: 'log', 'plot', or 'compare'")
    parser.add_argument("--port", default="COM3", help="BMS Serial Port (default: COM3)")
    parser.add_argument("--baud", type=int, default=115200, help="BMS Serial Baudrate (default: 115200)")
    parser.add_argument("--output", default="bms_telemetry_log.csv", help="Output CSV path (default: bms_telemetry_log.csv)")
    parser.add_argument("--input", default="bms_telemetry_log.csv", help="Input CSV path for plotting (default: bms_telemetry_log.csv)")
    parser.add_argument("--output-dir", default="plots", help="Directory to save generated charts (default: plots)")
    parser.add_argument("--sim", action="store_true", help="Force Simulation/Demo Mode (no serial hardware required)")
    parser.add_argument("--duration", type=int, default=0, help="Logging duration in seconds (default is unlimited for serial, 120s for simulation)")
    parser.add_argument("--ac-meter-wh", type=float, default=0.0, help="Total AC meter Watt-hours to calculate System Efficiency")
    parser.add_argument("--ac-meter-wh2", type=float, default=0.0, help="Total AC meter Watt-hours for the second file in compare mode")
    parser.add_argument("--dc-meter-wh", type=float, default=0.0, help="Total DC charger meter Watt-hours for Log 1")
    parser.add_argument("--dc-meter-wh2", type=float, default=0.0, help="Total DC charger meter Watt-hours for Log 2")
    parser.add_argument("--compare", default=None, help="Path to a second CSV file to compare against (used with --mode compare)")
    
    args = parser.parse_args()
    
    if args.mode == "log":
        log_data(args.port, args.baud, args.output, args.sim, args.duration)
    elif args.mode == "plot":
        plot_curves(args.input, args.output_dir, args.ac_meter_wh)
    elif args.mode == "compare":
        if not args.compare:
            print("Error: You must provide a second file using --compare <file.csv>")
        else:
            compare_logs(args.input, args.compare, args.ac_meter_wh, args.ac_meter_wh2, args.dc_meter_wh, args.dc_meter_wh2, args.output_dir)
            print("\nGenerating comparative plots for both logs...")
            
            # Extract basic names for prefixes
            name1 = os.path.splitext(os.path.basename(args.input))[0]
            name2 = os.path.splitext(os.path.basename(args.compare))[0]
            
            plot_curves(args.input, args.output_dir, args.ac_meter_wh, prefix=name1, show_plots=False)
            plot_curves(args.compare, args.output_dir, args.ac_meter_wh2, prefix=name2, show_plots=True)

if __name__ == "__main__":
    main()
