#!/usr/bin/env python3
"""
BMS Serial Plotter
------------------
A real-time visualization tool that reads battery telemetry data from an 
Arduino BMS (from bms.ino) via Serial or simulation, parses the readings, 
and plots the battery voltage over time with dynamic color coding:
  - GREEN: Charging (Current > 0.05 A)
  - RED: Discharging (Current < -0.05 A)
  - AMBER/GRAY: Idle

Features a side panel dashboard displaying Voltage, Current, SOC, Temperature, 
cell voltages, health statuses, and cycles. Includes a simulated demo mode 
in case the hardware is not connected.
"""

import sys
import time
import re
import threading
import queue
import random
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.animation import FuncAnimation

# Try importing serial (pyserial)
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("Warning: 'pyserial' package is not installed. Running in Demo Mode only.")

# Regular expression to parse the exact bms.ino display() output.
# Sample output:
# V_in:5.00V V_bat:12.30V C1:4.10V C2:4.10V C3:4.10V I:1.40A SOC:100.00% SOH1:100.00% H1:GOOD SOH2:100.00% H2:GOOD SOH3:100.00% H3:GOOD cycles:0.00 dac:4095
# 
# We use a key-value finder that is extremely robust against format changes.
BMS_KV_PATTERN = re.compile(r"(\w+):([-+]?\d*\.\d+|\d+|[a-zA-Z_]+)[VA%]*")


def parse_bms_line(line):
    """
    Parses a string line from BMS and returns a dictionary of values.
    """
    data = {}
    matches = BMS_KV_PATTERN.findall(line)
    for key, val in matches:
        # Convert numeric values to floats
        try:
            data[key] = float(val)
        except ValueError:
            data[key] = val  # Keep string for health status (e.g. H1:GOOD)
    return data


class BMSSimulator:
    """
    Simulates a 3-cell battery pack charge/discharge cycle.
    Generates serial messages matching the exact output of bms.ino's display().
    """
    def __init__(self):
        self.soc = 45.0  # start at 45% SOC
        self.capacity_ah = 7.8  # Parallel capacity
        self.cycle_count = 12.0
        self.cells_soc = [46.2, 45.0, 43.8] # slight imbalance
        self.cell_capacities = [2.6, 2.58, 2.62] # Ah
        self.cell_irs = [0.09, 0.11, 0.13] # Ohms (from bms.ino)
        self.soh = [98.5, 96.2, 99.0]
        self.health_labels = ["GOOD", "GOOD", "GOOD"]
        self.dac = 2048
        
        # OCV-SOC lookup points to simulate realistic battery chemistry
        self.soc_pts = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0]
        self.ocv_pts = [3.1, 3.25, 3.4, 3.55, 3.65, 3.73, 3.82, 3.9, 4.0, 4.05, 4.1]
        
        self.time_counter = 0
        self.current_state = "DISCHARGE"  # Start by discharging
        self.state_timer = 0

    def get_ocv(self, soc):
        # Convert percentage (0-100) to fraction (0-1)
        fraction = soc / 100.0
        fraction = max(0.0, min(1.0, fraction))
        return np.interp(fraction, self.soc_pts, self.ocv_pts)

    def step(self):
        """
        Runs one step (1 second) of the simulation and returns a formatted bms.ino string.
        """
        self.time_counter += 1
        self.state_timer += 1
        
        # Toggle state every 45 seconds for demonstration purposes
        if self.state_timer >= 45:
            self.state_timer = 0
            if self.current_state == "DISCHARGE":
                self.current_state = "CHARGE"
            else:
                self.current_state = "DISCHARGE"
        
        if self.current_state == "CHARGE":
            # CC-CV charging simulation
            v_avg = sum([self.get_ocv(c_soc) for c_soc in self.cells_soc]) / 3.0
            
            if v_avg < 4.05:
                # CC Mode: constant current splits in parallel
                total_current = 4.2  # Max parallel current
                self.dac = int(4095 - (total_current * 400)) # dummy dac calculation
            else:
                # CV Mode: current decays exponentially
                total_current = max(0.05, 4.2 * (4.1 - v_avg) / 0.05)
                self.dac = int(total_current * 900)
            
            # Distribute current in parallel (highly simplified physical model)
            for i in range(3):
                # Cells with lower SOC/OCV draw more current in parallel
                ocv_i = self.get_ocv(self.cells_soc[i])
                # Current share based on resistance and voltage difference
                self.cells_soc[i] += (total_current / 3.0) * (1.0 / 3600.0) * 100.0
                self.cells_soc[i] = min(100.0, self.cells_soc[i])
                
            self.soc = sum(self.cells_soc) / 3.0
            v_in = 5.0  # Charger connected
            
        else:
            # Series discharging simulation (load is on)
            total_current = -1.5  # Negative current for discharging
            self.dac = 4095  # DAC fully open / disabled during discharge
            
            # Series current is identical through all cells
            for i in range(3):
                self.cells_soc[i] += total_current * (1.0 / 3600.0) * 100.0
                self.cells_soc[i] = max(0.0, self.cells_soc[i])
                
            self.soc = min(self.cells_soc)  # In series, weak cell determines pack SOC
            v_in = 0.0  # Charger disconnected
        
        # Calculate cell voltages (OCV + IR drop)
        cell_voltages = []
        for i in range(3):
            ocv = self.get_ocv(self.cells_soc[i])
            ir_drop = (total_current / 3.0 if self.current_state == "CHARGE" else total_current) * self.cell_irs[i]
            v_term = ocv + ir_drop
            # Clamp cell terminal voltages to realistic boundaries
            cell_voltages.append(max(2.8, min(4.25, v_term)))
            
        # Calculate total pack voltage
        if self.current_state == "CHARGE":
            # In parallel, v_bat is cell terminal voltage (roughly average)
            v_bat = sum(cell_voltages) / 3.0
        else:
            # In series, v_bat is sum of cell terminal voltages
            v_bat = sum(cell_voltages)
            
        # SOH calculation: slightly degrade internal resistances over time
        for i in range(3):
            # simulate very slow wear
            self.cell_irs[i] += 0.000001
            # Recalculate SOH using bms.ino formula (fresh_ir = 0.09/0.11/0.13, dead_ir = 0.15)
            fresh_ir = 0.09 + i * 0.02
            self.soh[i] = 100.0 - ((self.cell_irs[i] - fresh_ir) / (0.15 - fresh_ir)) * 100.0
            self.soh[i] = max(0.0, min(100.0, self.soh[i]))
            
            if self.soh[i] > 85.0:
                self.health_labels[i] = "GOOD"
            elif self.soh[i] > 60.0:
                self.health_labels[i] = "DEGRADING"
            else:
                self.health_labels[i] = "DEAD"

        # Increment cycle count slowly
        if self.current_state == "DISCHARGE":
            self.cycle_count += abs(total_current) / (3600.0 * self.capacity_ah)
            
        # Format exact output string matching bms.ino's display()
        bms_str = (
            f"V_in:{v_in:.2f}V V_bat:{v_bat:.2f}V "
            f"C1:{cell_voltages[0]:.2f}V C2:{cell_voltages[1]:.2f}V C3:{cell_voltages[2]:.2f}V "
            f"I:{total_current:.2f}A SOC:{self.soc:.2f}% "
            f"SOH1:{self.soh[0]:.2f}% H1:{self.health_labels[0]} "
            f"SOH2:{self.soh[1]:.2f}% H2:{self.health_labels[1]} "
            f"SOH3:{self.soh[2]:.2f}% H3:{self.health_labels[2]} "
            f"cycles:{self.cycle_count:.2f} dac:{self.dac}"
        )
        return bms_str


class BMSDataReceiver:
    """
    Spawns a thread to receive and parse battery data from the selected Serial Port
    or simulated source, piping the dictionary objects into a thread-safe Queue.
    """
    def __init__(self, port=None, baudrate=115200, use_demo=False):
        self.port = port
        self.baudrate = baudrate
        self.use_demo = use_demo
        self.data_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.serial_conn = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass

    def _run(self):
        if self.use_demo:
            print("Starting BMS in Simulated Demo Mode...")
            sim = BMSSimulator()
            while self.running:
                # Step the simulator
                bms_line = sim.step()
                parsed_data = parse_bms_line(bms_line)
                
                # Dynamic Temperature simulation (based on current and resistance heating)
                # Not printed by bms.ino display(), so we add it in our parser pipeline
                current = parsed_data.get('I', 0.0)
                temp = 25.0 + 3.5 * (current ** 2) * 0.1 + random.uniform(-0.1, 0.1)
                parsed_data['Temp'] = temp
                
                self.data_queue.put((time.time(), parsed_data))
                time.sleep(1.0)
        else:
            print(f"Connecting to BMS on port {self.port} at {self.baudrate} baud...")
            try:
                self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1.0)
                # Flush initial buffers
                self.serial_conn.reset_input_buffer()
            except Exception as e:
                print(f"Error opening serial port {self.port}: {e}")
                print("Falling back to Demo Mode...")
                self.use_demo = True
                self._run()
                return

            print("Serial connection established! Listening for data...")
            while self.running:
                try:
                    if self.serial_conn.in_waiting > 0:
                        raw_line = self.serial_conn.readline()
                        line = raw_line.decode('utf-8', errors='ignore').strip()
                        if line:
                            # Print raw incoming line to terminal for debugging
                            print(f"[RAW SERIAL]: {line}")
                            parsed_data = parse_bms_line(line)
                            
                            # Ensure we actually parsed some fields (must contain at least V_bat)
                            if 'V_bat' in parsed_data:
                                # Inject dynamic temperature since bms.ino has no physical sensor output
                                current = parsed_data.get('I', 0.0)
                                temp = 25.0 + 3.0 * (current ** 2) * 0.1 + random.uniform(-0.05, 0.05)
                                parsed_data['Temp'] = temp
                                
                                self.data_queue.put((time.time(), parsed_data))
                except Exception as e:
                    print(f"Error reading serial line: {e}")
                    time.sleep(0.5)


def list_serial_ports():
    """
    Scans and returns list of available COM / TTY ports.
    """
    if not SERIAL_AVAILABLE:
        return []
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]


def main():
    print("=========================================")
    print("    Arduino BMS Real-Time Serial Plotter ")
    print("=========================================\n")
    
    # 1. Select Port
    port_choice = None
    use_demo = False
    
    if SERIAL_AVAILABLE:
        ports = list_serial_ports()
        if ports:
            print("Available Serial Ports:")
            for idx, port in enumerate(ports):
                print(f" [{idx}] {port}")
            print(f" [{len(ports)}] Run in Simulated Demo Mode")
            
            try:
                # Wait for user input with prompt
                choice = input(f"\nSelect port index (0-{len(ports)}): ").strip()
                if not choice:
                    use_demo = True
                elif int(choice) == len(ports):
                    use_demo = True
                else:
                    port_choice = ports[int(choice)]
            except (ValueError, IndexError):
                print("Invalid selection. Defaulting to Demo Mode.")
                use_demo = True
        else:
            print("No serial ports detected. Defaulting to Simulated Demo Mode.")
            use_demo = True
    else:
        use_demo = True

    # 2. Start Receiver
    receiver = BMSDataReceiver(port=port_choice, use_demo=use_demo)
    receiver.start()
    
    # 3. Setup Matplotlib Plot
    plt.style.use('dark_background')  # Premium dark theme
    
    # GridSpec layout: Left represents Plot, Right represents Text Dashboard
    fig = plt.figure(figsize=(13, 7.5))
    fig.canvas.manager.set_window_title("BMS Real-Time Telemetry Monitor")
    
    gs = fig.add_gridspec(1, 4)
    ax_plot = fig.add_subplot(gs[0, :3])  # 3/4 width for voltage plot
    ax_dash = fig.add_subplot(gs[0, 3])   # 1/4 width for stats sidebar
    ax_dash.axis('off')                   # Remove axes frame and ticks from sidebar
    
    # Plot formatting
    ax_plot.set_title("Battery Pack Voltage & Cell Tracking", fontsize=14, pad=15, color='#E0E0E0', fontweight='bold')
    ax_plot.set_xlabel("Elapsed Time (s)", fontsize=11, color='#B0B0B0')
    ax_plot.set_ylabel("Voltage (V)", fontsize=11, color='#B0B0B0')
    ax_plot.grid(True, linestyle='--', color='#444444', alpha=0.7)
    
    # Initialize empty data structures
    history = {
        'time_rel': [],
        'time_abs': [],
        'v_bat': [],
        'current': [],
        'soc': [],
        'temp': [],
        'cells': [[], [], []],
        'cycles': []
    }
    
    start_time_ref = [None]  # Mutable cell to hold reference start timestamp
    
    # Setup elements in plot
    line_c1, = ax_plot.plot([], [], label='Cell 1 (V)', color='#42A5F5', linestyle=':', alpha=0.7)
    line_c2, = ax_plot.plot([], [], label='Cell 2 (V)', color='#26A69A', linestyle=':', alpha=0.7)
    line_c3, = ax_plot.plot([], [], label='Cell 3 (V)', color='#AB47BC', linestyle=':', alpha=0.7)
    
    # Add dummy legend handles for charging/discharging lines
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color='#00E676', lw=2.5, label='Charging Mode (V_bat)'),
        Line2D([0], [0], color='#FF1744', lw=2.5, label='Discharging Mode (V_bat)'),
        Line2D([0], [0], color='#757575', lw=2, label='Idle Mode (V_bat)'),
        Line2D([0], [0], color='#42A5F5', lw=1.5, ls=':', label='Cell 1 Voltage'),
        Line2D([0], [0], color='#26A69A', lw=1.5, ls=':', label='Cell 2 Voltage'),
        Line2D([0], [0], color='#AB47BC', lw=1.5, ls=':', label='Cell 3 Voltage')
    ]
    ax_plot.legend(handles=legend_elements, loc='upper left', framealpha=0.2)
    
    lc_container = {'lc': None}  # Holds reference to the dynamic LineCollection
    
    # Create text objects in sidebar dashboard
    dash_texts = {}
    y_pos = 0.95
    line_spacing = 0.06
    
    # Dashboard Headers & Title
    ax_dash.text(0.0, y_pos, "BMS STATS", fontsize=15, fontweight='bold', color='#FFFFFF')
    y_pos -= line_spacing * 1.5
    
    dashboard_fields = [
        ("Status", "IDLE", '#FFB300'),
        ("SOC", "0.00 %", '#FFFFFF'),
        ("V_bat", "0.00 V", '#FFFFFF'),
        ("Current", "0.00 A", '#FFFFFF'),
        ("Temp", "25.0 °C", '#FFFFFF'),
        ("Cell 1", "0.00 V", '#42A5F5'),
        ("Cell 2", "0.00 V", '#26A69A'),
        ("Cell 3", "0.00 V", '#AB47BC'),
        ("Cycles", "0.00", '#FFFFFF'),
        ("DAC Output", "0", '#FFFFFF'),
    ]
    
    for label, val, color in dashboard_fields:
        ax_dash.text(0.0, y_pos, f"{label}:", fontsize=11, fontweight='medium', color='#B0B0B0')
        txt_val = ax_dash.text(0.48, y_pos, val, fontsize=12, fontweight='bold', color=color)
        dash_texts[label] = txt_val
        y_pos -= line_spacing
        
    # Info note at bottom of sidebar
    ax_dash.text(0.0, 0.05, f"Source: {'Simulation (Demo)' if use_demo else port_choice}\nBaudrate: 115200 bps\nClose window to exit.", 
                 fontsize=9, color='#757575', style='italic')

    def update_plot(frame):
        # 1. Drain the queue and populate history
        new_data_points = []
        while not receiver.data_queue.empty():
            new_data_points.append(receiver.data_queue.get())
            
        if not new_data_points and not history['time_rel']:
            return line_c1, line_c2, line_c3
            
        for timestamp, data in new_data_points:
            if start_time_ref[0] is None:
                start_time_ref[0] = timestamp
                
            history['time_abs'].append(timestamp)
            history['time_rel'].append(timestamp - start_time_ref[0])
            history['v_bat'].append(data.get('V_bat', 0.0))
            history['current'].append(data.get('I', 0.0))
            history['soc'].append(data.get('SOC', 0.0))
            history['temp'].append(data.get('Temp', 25.0))
            history['cycles'].append(data.get('cycles', 0.0))
            
            history['cells'][0].append(data.get('C1', 0.0))
            history['cells'][1].append(data.get('C2', 0.0))
            history['cells'][2].append(data.get('C3', 0.0))
            
        # Limit history size to 300 points to keep graph fast and clean
        max_points = 300
        if len(history['time_rel']) > max_points:
            for k in ['time_rel', 'time_abs', 'v_bat', 'current', 'soc', 'temp', 'cycles']:
                history[k] = history[k][-max_points:]
            for idx in range(3):
                history['cells'][idx] = history['cells'][idx][-max_points:]
                
        # 2. Update line plots for C1, C2, C3
        line_c1.set_data(history['time_rel'], history['cells'][0])
        line_c2.set_data(history['time_rel'], history['cells'][1])
        line_c3.set_data(history['time_rel'], history['cells'][2])
        
        # 3. Update V_bat segmented line colors
        if len(history['time_rel']) >= 2:
            t_np = np.array(history['time_rel'])
            v_np = np.array(history['v_bat'])
            i_np = np.array(history['current'])
            
            # Form contiguous segment lines
            pts = np.array([t_np, v_np]).T.reshape(-1, 1, 2)
            segments = np.concatenate([pts[:-1], pts[1:]], axis=1)
            
            # Map current value to colors
            colors = []
            for i in range(len(i_np) - 1):
                curr = i_np[i]
                if curr > 0.05:
                    colors.append('#00E676')  # Green (Charging)
                elif curr < -0.05:
                    colors.append('#FF1744')  # Red (Discharging)
                else:
                    colors.append('#757575')  # Gray (Idle)
                    
            if lc_container['lc'] is not None:
                lc_container['lc'].remove()
                
            lc_container['lc'] = LineCollection(segments, colors=colors, linewidths=2.5)
            ax_plot.add_collection(lc_container['lc'])
            
        # 4. Rescale X & Y limits dynamically
        ax_plot.set_xlim(max(0, history['time_rel'][-1] - 60), history['time_rel'][-1] + 5)
        
        # Get min and max voltages from both pack and cells to auto-scale Y axis nicely
        all_v = history['v_bat'] + history['cells'][0] + history['cells'][1] + history['cells'][2]
        if all_v:
            y_min = min(all_v) - 0.2
            y_max = max(all_v) + 0.2
            ax_plot.set_ylim(max(2.5, y_min), min(14.0, y_max))
            
        # 5. Update Sidebar Dashboard texts with latest values
        if new_data_points:
            _, latest = new_data_points[-1]
            
            # Determine Charging / Discharging / Idle status
            curr = latest.get('I', 0.0)
            if curr > 0.05:
                status = "CHARGING"
                status_color = "#00E676"
            elif curr < -0.05:
                status = "DISCHARGING"
                status_color = "#FF1744"
            else:
                status = "IDLE"
                status_color = "#FFB300"
                
            dash_texts["Status"].set_text(status)
            dash_texts["Status"].set_color(status_color)
            
            dash_texts["SOC"].set_text(f"{latest.get('SOC', 0.0):.2f} %")
            dash_texts["V_bat"].set_text(f"{latest.get('V_bat', 0.0):.2f} V")
            dash_texts["Current"].set_text(f"{latest.get('I', 0.0):.2f} A")
            
            # Retrieve injected temperature
            latest_temp = history['temp'][-1]
            dash_texts["Temp"].set_text(f"{latest_temp:.1f} °C")
            if latest_temp > 40.0:
                dash_texts["Temp"].set_color("#FF1744") # Red for hot
            else:
                dash_texts["Temp"].set_color("#FFFFFF")
                
            dash_texts["Cell 1"].set_text(f"{latest.get('C1', 0.0):.2f} V")
            dash_texts["Cell 2"].set_text(f"{latest.get('C2', 0.0):.2f} V")
            dash_texts["Cell 3"].set_text(f"{latest.get('C3', 0.0):.2f} V")
            dash_texts["Cycles"].set_text(f"{latest.get('cycles', 0.0):.2f}")
            dash_texts["DAC Output"].set_text(f"{int(latest.get('dac', 0))}")
            
        return line_c1, line_c2, line_c3

    # Run the animation at 5 FPS (200ms interval) to keep CPU overhead low
    anim = FuncAnimation(fig, update_plot, interval=200, save_count=100)
    
    # Handle clean termination when closing the plot window
    def on_close(event):
        print("\nWindow closed. Stopping threads and exiting...")
        receiver.stop()
        sys.exit(0)
        
    fig.canvas.mpl_connect('close_event', on_close)
    
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting due to KeyboardInterrupt...")
        sys.exit(0)
