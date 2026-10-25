#!/usr/bin/env python3
"""
SCADA BMS Telemetry Server - ESP32 Real-Device Mode
----------------------------------------------------
- Receives REAL telemetry from ESP32 via HTTP POST to /api/telemetry
- Serves BMS dashboard at http://localhost:8000/
- No simulation data is generated
- Dashboard shows "Battery Not Connected" until ESP32 posts valid data
- ESP32 connectivity timeout: if no POST in 5 seconds, show "Device Offline"
"""

import os
import sys
import time
import json
import csv
import io
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ─── State ────────────────────────────────────────────────────────────────────
# Start with disconnected state - only real ESP32 data will update this
latest_telemetry = {
    "connected": False,
    "cells": [],
    "cellCount": 0,
    "batteryVoltage": 0.0,
    "inputVoltage": 0.0,
    "current": 0.0,
    "soc": 0.0,
    "soh": 0.0,
    "configuration": "--",
    "timestamp": 0.0
}

telemetry_history = []
MAX_HISTORY = 14400 # 4 hours of history at 1Hz (4 * 60 * 60)
telemetry_lock = threading.Lock()
pending_config = {} # Holds config updates from dashboard until ESP32 retrieves them

# Tracks when the last valid ESP32 POST arrived (for offline detection)
last_esp32_post_time = 0.0

# Consecutive disconnected counter — prevents a momentary glitch (e.g. config update pause)
# from triggering the "Battery Not Connected" overlay. Only show it after 3 consecutive
# disconnected packets in a row.
disconnected_count = 0
DISCONNECTED_THRESHOLD = 3


# ─── HTTP Request Handler ─────────────────────────────────────────────────────
class SCADAHTTPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        dashboard_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")
        super().__init__(*args, directory=dashboard_dir, **kwargs)

    def log_message(self, format, *args):
        # Only log POST requests so the console isn't flooded by GET polls
        if args and "POST" in str(args[0]):
            super().log_message(format, *args)

    def send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]  # Strip query params for routing

        # ── /api/telemetry ──────────────────────────────────────────────────
        if path == "/api/telemetry":
            global last_esp32_post_time
            elapsed = time.time() - last_esp32_post_time

            with telemetry_lock:
                data = dict(latest_telemetry)

            # If no data ever received from ESP32, serve disconnected state
            if last_esp32_post_time == 0.0:
                self.send_json(200, {
                    "connected": False,
                    "cells": [],
                    "cellCount": 0,
                    "batteryVoltage": 0.0,
                    "inputVoltage": 0.0,
                    "current": 0.0,
                    "soc": 0.0,
                    "soh": 0.0,
                    "configuration": "--",
                    "esp32_online": False,
                    "timestamp": time.time()
                })
                return

            # If ESP32 hasn't posted in 5 seconds → device offline
            if elapsed > 5.0:
                data["esp32_online"] = False
            else:
                data["esp32_online"] = True

            self.send_json(200, data)
            return

        # ── /api/history ────────────────────────────────────────────────────
        elif path == "/api/history":
            # Determine timeframe from query params (default 1m = 60 points)
            tf = "1m"
            if "?" in self.path:
                q = self.path.split("?")[1]
                for kv in q.split("&"):
                    if kv.startswith("tf="):
                        tf = kv.split("=")[1]
            
            points = 60
            if tf == "1m": points = 60
            elif tf == "5m": points = 300
            elif tf == "1h": points = 3600
            elif tf == "24h": points = 14400 # We only store 4 hours max

            with telemetry_lock:
                history = list(telemetry_history[-points:])
            self.send_json(200, history)
            return

        # ── /api/status ─────────────────────────────────────────────────────
        elif path == "/api/status":
            elapsed = time.time() - last_esp32_post_time
            self.send_json(200, {
                "esp32_online": last_esp32_post_time > 0 and elapsed < 5.0,
                "last_post_ago_seconds": round(elapsed, 1),
                "total_records": len(telemetry_history)
            })
            return

        # ── /api/export/csv ─────────────────────────────────────────────────
        elif path == "/api/export/csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Timestamp", "Connected", "CellCount", "Config",
                "PackVoltage_V", "InputVoltage_V", "Current_A", "SOC_pct", "SOH_pct"
            ])
            with telemetry_lock:
                for row in telemetry_history:
                    writer.writerow([
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row.get("timestamp", 0))),
                        row.get("connected"), row.get("cellCount"), row.get("configuration"),
                        row.get("batteryVoltage"), row.get("inputVoltage"),
                        row.get("current"), row.get("soc"), row.get("soh")
                    ])
            body = output.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", "attachment; filename=bms_log.csv")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        # ── Serve static dashboard files ─────────────────────────────────────
        else:
            super().do_GET()

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        global latest_telemetry, last_esp32_post_time, pending_config, disconnected_count

        if self.path.startswith("/api/telemetry"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_json(400, {"error": "Empty body"})
                return

            try:
                raw = self.rfile.read(content_length)
                data = json.loads(raw.decode("utf-8"))

                # Validate required keys exist in payload
                if "connected" not in data:
                    self.send_json(400, {"error": "Missing 'connected' field"})
                    return

                # Stamp server-side receive time
                data["timestamp"] = time.time()

                # Debounce false disconnects: only propagate connected=False
                # after DISCONNECTED_THRESHOLD consecutive false packets.
                # A single false reading (e.g. during config update pause) is ignored.
                if not data.get("connected", False):
                    disconnected_count += 1
                    if disconnected_count < DISCONNECTED_THRESHOLD:
                        # Preserve the last known good connected state in latest_telemetry
                        # but still update the history record
                        data["connected"] = latest_telemetry.get("connected", False)
                        data["cells"] = latest_telemetry.get("cells", [])
                else:
                    disconnected_count = 0  # Reset counter on good packet

                # REPLACE latest_telemetry entirely (not merge/update)
                with telemetry_lock:
                    latest_telemetry = data
                    last_esp32_post_time = time.time()
                    record = dict(data)
                    telemetry_history.append(record)
                    if len(telemetry_history) > MAX_HISTORY:
                        telemetry_history.pop(0)

                print(f"[ESP32] POST received | connected={data.get('connected')} | "
                      f"cells={data.get('cellCount', '?')} | "
                      f"SOC={data.get('soc', '?')}% | "
                      f"Vbat={data.get('batteryVoltage', '?')}V")

                response_payload = {"status": "ok", "received": data.get("cellCount", 0)}
                
                with telemetry_lock:
                    if pending_config:
                        response_payload["pending_config"] = dict(pending_config)
                        print(f"[Server] Sending pending config to ESP32: {pending_config}")
                        pending_config.clear()

                self.send_json(200, response_payload)

            except json.JSONDecodeError as e:
                print(f"[ERROR] Invalid JSON from ESP32: {e}")
                self.send_json(400, {"error": f"Invalid JSON: {str(e)}"})
            except Exception as e:
                print(f"[ERROR] POST handler exception: {e}")
                self.send_json(500, {"error": str(e)})

        # ── /api/config ──────────────────────────────────────────────────────
        elif self.path.startswith("/api/config"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_json(400, {"error": "Empty body"})
                return

            try:
                raw = self.rfile.read(content_length)
                config_data = json.loads(raw.decode("utf-8"))
                
                with telemetry_lock:
                    pending_config.update(config_data)
                    print(f"[Dashboard] Received new config, waiting to push to ESP32: {pending_config}")

                self.send_json(200, {"status": "config_queued"})
            except json.JSONDecodeError as e:
                self.send_json(400, {"error": f"Invalid JSON: {str(e)}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
        else:
            self.send_json(404, {"error": "Not found"})

    # ── OPTIONS (CORS preflight) ──────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def run_server(port=8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, SCADAHTTPRequestHandler)

    # Find and display the machine's local IP for easy ESP32 configuration
    import socket
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "127.0.0.1"

    print("=" * 60)
    print("  SCADA BMS Telemetry Server — ESP32 Real-Device Mode")
    print("=" * 60)
    print(f"  Dashboard:     http://localhost:{port}/")
    print(f"  Telemetry GET: http://localhost:{port}/api/telemetry")
    print(f"  Status:        http://localhost:{port}/api/status")
    print(f"  CSV Export:    http://localhost:{port}/api/export/csv")
    print("-" * 60)
    print(f"  ESP32 should POST to:")
    print(f"    http://{local_ip}:{port}/api/telemetry")
    print("-" * 60)
    print("  Waiting for ESP32 connection...")
    print("  Dashboard will show 'Battery Not Connected' until ESP32 posts data.")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SCADA server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server(8000)
