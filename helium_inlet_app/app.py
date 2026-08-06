'''
This script runs the telemetry, control loop, and automated alternating trap state machine
for the Helium cold-trap/MS instrument, serving real-time updates to the web interface.
'''

import asyncio
import math
import threading
import time
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import serial

# Web App Initialization
app = FastAPI(title="Helium Inlet Control System")
templates = Jinja2Templates(directory="templates")

# Log Window Management
MAX_LOG_ENTRIES = 50
system_logs = []


def log_event(message: str, level: str = "INFO"):
    """Appends a timestamped log entry to the event queue."""
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "level": level, "msg": message}
    system_logs.append(entry)
    if len(system_logs) > MAX_LOG_ENTRIES:
        system_logs.pop(0)


log_event("Control hub initialized. State Machine & Telemetry starting...", "INFO")

# System Timers & Configuration Parameters (in seconds)
CFG = {
    "COLD_TEMP_THRESHOLD": 100.0,  # Kelvin/Celsius target for Stirling cold state
    "SAMPLE_TIME_A_MINS": 10,     # XX minutes sampling on Trap A
    "PRECOOL_B_TIME_MINS": 5,     # XX minutes start cooling B before switch
    "ISOLATE_B_TIME_MINS": 1,     # YY minutes isolate B before switch
    "BURP_DELAY_SECS": 15,        # Wait seconds for gas burp before starting waste turbo
    "REGEN_TIME_MINS": 8,         # AA minutes heating/pumping trap during regen
    "WATCHDOG_INTERVAL_SECS": 3   # Send 24V watchdog pulse every 3s
}

# Initial Telemetry & State Machine Data Structure
telemetry_data = {
    "status": "Initializing...",
    "device": "Disconnected",
    "timestamp": "Waiting for data...",
    "logs": system_logs,
    
    # Automated Control State Machine Status
    "fsm": {
        "enabled": False,
        "state": "IDLE",
        "phase_desc": "System Idle / Manual Mode",
        "active_trap": "NONE",
        "timer_secs": 0,
        "cycle_count": 0
    },
    
    # Hardware Outputs / Valves / Relays
    "control": {
        "v_waste_a": False,      # False=CLOSED, True=OPEN
        "v_waste_b": False,      # False=CLOSED, True=OPEN
        "v_ms_inlet": "A",       # "A" or "B"
        "cov_valve": "SAMPLE",   # "SAMPLE" or "IRG"
        "heater_a": False,       # True=ON
        "heater_b": False,       # True=ON
        "turbo_waste": True,     # True=ON (Protect mode turns OFF during burps)
        "stirling_a_cmd": False, # Cooling active command
        "stirling_b_cmd": False,
        "watchdog_ok": True
    },

    # Stirling Serial Telemetry
    "stirling_a": {"temp": 295.0, "power": 0.0, "status": "OFF"},
    "stirling_b": {"temp": 295.0, "power": 0.0, "status": "OFF"},

    # Sensor Channels
    "ch104": "---.-- °C", "ch104_val": None, # Engine A HR
    "ch103": "---.-- °C", "ch103_val": None, # Engine A PV
    "ch101": "---.-- °C", "ch101_val": None, # Engine B HR
    "ch102": "---.-- °C", "ch102_val": None, # Engine B PV
    "ch115_p": "---.--- Torr", "ch115_p_val": None, "ch115_v": "---.-- V", "ch113": "---.-- V", # Chamber
    "ch116_p": "---.--- Torr", "ch116_p_val": None, "ch116_v": "---.-- V", "ch112": "---.-- V", # Trap
    "ch118_p": "N/A", "ch118_p_val": None, "ch118_v": "N/A", # HiVac Convectron
    "ch119_p": "---.--- Torr", "ch119_p_val": None, "ch119_v": "---.-- V", # Trap LoVac Convectron
}


def parse_scpi_list(raw_response: str):
    """Parses comma-separated SCPI float responses safely."""
    if not raw_response:
        return []
    results = []
    for item in raw_response.split(","):
        try:
            results.append(float(item.strip()))
        except ValueError:
            results.append(None)
    return results


def format_temp(val):
    if val is None:
        return "---.-- °C"
    if val > 9e9:
        return "OPEN / NC"
    return f"{val:.2f} °C"


def calc_trap_penning_pressure(volts):
    if volts is None:
        return "---.--- Torr", None
    try:
        pressure_mbar = 10 ** ((volts * 0.875) - 10.75)
        pressure_torr = pressure_mbar * 0.750062
        return f"{pressure_torr:.2e} Torr", pressure_torr
    except Exception:
        return "Error", None


def calc_chamber_aim_sl_pressure(volts):
    if volts is None:
        return "---.--- Torr", None
    if volts < 2.00:
        return "< 7.5e-09 Torr", 7.5e-9
    if volts > 10.00:
        return "> 7.5e-03 Torr", 7.5e-3

    aim_sl_table_torr = [
        (2.00, 7.5e-9),  (2.50, 1.8e-8), (3.00, 4.4e-8), (3.20, 6.1e-8),
        (3.40, 8.3e-8),  (3.60, 1.1e-7), (3.80, 1.6e-7), (4.00, 2.2e-7),
        (4.20, 3.0e-7),  (4.40, 4.1e-7), (4.60, 5.5e-7), (4.80, 7.4e-7),
        (5.00, 9.8e-7),  (5.20, 1.3e-6), (5.40, 1.7e-6), (5.60, 2.1e-6),
        (5.80, 2.7e-6),  (6.00, 3.4e-6), (6.20, 4.2e-6), (6.40, 5.2e-6),
        (6.60, 6.3e-6),  (6.80, 7.5e-6), (7.00, 9.0e-6), (7.20, 1.1e-5),
        (7.40, 1.3e-5),  (7.60, 1.5e-5), (7.80, 1.8e-5), (8.00, 2.2e-5),
        (8.20, 2.6e-5),  (8.40, 3.2e-5), (8.60, 4.3e-5), (8.80, 5.9e-5),
        (9.00, 9.0e-5),  (9.20, 1.4e-4), (9.40, 2.5e-4), (9.60, 5.0e-4),
        (9.80, 1.3e-3),  (9.90, 2.7e-3), (10.00, 7.5e-3)
    ]

    for v, p in aim_sl_table_torr:
        if abs(volts - v) < 0.001:
            return f"{p:.2e} Torr", p

    for i in range(len(aim_sl_table_torr) - 1):
        v1, p1 = aim_sl_table_torr[i]
        v2, p2 = aim_sl_table_torr[i+1]
        if v1 < volts < v2:
            log_p1 = math.log10(p1)
            log_p2 = math.log10(p2)
            log_p = log_p1 + (volts - v1) * ((log_p2 - log_p1) / (v2 - v1))
            pressure = 10 ** log_p
            return f"{pressure:.2e} Torr", pressure

    return "Error", None


def calc_convectron_375_pressure(volts):
    if volts is None:
        return "---.--- Torr", None
    if volts < 0.0:
        return "< 1.00e-04 Torr", 1.0e-4
    if volts > 7.1:
        return "> 1000 Torr", 1000.0
    try:
        pressure_torr = 10 ** (volts - 4)
        return f"{pressure_torr:.2e} Torr", pressure_torr
    except Exception:
        return "Error", None


# --- AUTOMATED CONTROL STATE MACHINE ---
def run_control_state_machine():
    """1-Second State Machine handling alternating traps, valve sequencing, and interlocks."""
    global telemetry_data

    fsm = telemetry_data["fsm"]
    ctrl = telemetry_data["control"]

    if not fsm["enabled"]:
        fsm["state"] = "IDLE"
        fsm["phase_desc"] = "Manual Control Mode"
        return

    fsm["timer_secs"] += 1
    t = fsm["timer_secs"]

    # Safety Interlock check: Over-temperature guard
    temp_a = telemetry_data.get("ch103_val") or 25.0
    temp_b = telemetry_data.get("ch102_val") or 25.0
    if temp_a > 60.0 or temp_b > 60.0:
        log_event("SAFETY INTERLOCK TRIP: High temperature detected! Shutting off Stirlings & Heaters.", "WARN")
        ctrl["stirling_a_cmd"] = False
        ctrl["stirling_b_cmd"] = False
        ctrl["heater_a"] = False
        ctrl["heater_b"] = False
        fsm["enabled"] = False
        fsm["state"] = "FAULT"
        return

    # --- STATE SEQUENCER ---
    # 1. START COOLING ENGINE A
    if fsm["state"] == "START_COOLING_A":
        fsm["phase_desc"] = "Cooling Engine A to Waste"
        fsm["active_trap"] = "A"
        ctrl["stirling_a_cmd"] = True
        ctrl["v_waste_a"] = True  # Pumping to waste
        ctrl["v_waste_b"] = True
        ctrl["heater_a"] = False
        ctrl["heater_b"] = False

        if temp_a <= CFG["COLD_TEMP_THRESHOLD"] or t >= 300: # Wait until cold
            log_event("Engine A Cold. Isolating from waste & switching to MS Inlet.", "SUCCESS")
            fsm["state"] = "SAMPLE_A"
            fsm["timer_secs"] = 0

    # 2. SAMPLE ENGINE A -> MS
    elif fsm["state"] == "SAMPLE_A":
        fsm["phase_desc"] = f"Sampling Engine A -> MS ({t}s / {CFG['SAMPLE_TIME_A_MINS']*60}s)"
        ctrl["v_waste_a"] = False  # Isolate A from waste
        ctrl["v_ms_inlet"] = "A"   # Route A to MS

        # Near end of A sampling, start cooling Engine B to waste
        if t >= (CFG["SAMPLE_TIME_A_MINS"] * 60 - CFG["PRECOOL_B_TIME_MINS"] * 60):
            ctrl["stirling_b_cmd"] = True
            ctrl["v_waste_b"] = True  # Engine B pumps to waste while cooling

        if t >= (CFG["SAMPLE_TIME_A_MINS"] * 60 - CFG["ISOLATE_B_TIME_MINS"] * 60):
            ctrl["v_waste_b"] = False # Isolate B from waste right before switch

        if t >= CFG["SAMPLE_TIME_A_MINS"] * 60:
            log_event("Engine A sample time complete. Switching MS Inlet to Engine B.", "INFO")
            fsm["state"] = "SWITCH_TO_B"
            fsm["timer_secs"] = 0

    # 3. SWITCH TO ENGINE B & REGENERATE ENGINE A
    elif fsm["state"] == "SWITCH_TO_B":
        fsm["phase_desc"] = "Switching to Engine B & Desorbing/Burping Engine A"
        ctrl["v_ms_inlet"] = "B"
        ctrl["stirling_a_cmd"] = False # Shut off cooling Engine A
        ctrl["v_waste_a"] = True       # Open A to waste
        ctrl["heater_a"] = True        # Heat Trap A
        ctrl["turbo_waste"] = False    # Turn OFF waste turbo during initial gas burp

        if t >= CFG["BURP_DELAY_SECS"]:
            log_event("Gas burp passed. Turning waste turbo ON for Engine A regeneration.", "INFO")
            ctrl["turbo_waste"] = True
            fsm["state"] = "REGEN_A_PUMP"
            fsm["timer_secs"] = 0

    # 4. REGENERATE PUMP ENGINE A
    elif fsm["state"] == "REGEN_A_PUMP":
        fsm["phase_desc"] = f"Baking/Pumping Trap A ({t}s / {CFG['REGEN_TIME_MINS']*60}s)"
        if t >= CFG["REGEN_TIME_MINS"] * 60:
            log_event("Engine A regeneration complete. Preparing Engine A cooling sequence.", "SUCCESS")
            ctrl["heater_a"] = False
            fsm["state"] = "START_COOLING_A"
            fsm["timer_secs"] = 0
            fsm["cycle_count"] += 1


# --- BACKGROUND HARDWARE WORKER ---
def serial_hardware_loop():
    """Continuous background thread querying Agilent 34970A and updating state machine."""
    global telemetry_data

    SERIAL_PORT = "/dev/ttyUSB0"
    BAUD_RATE = 57600
    TC_CHANNELS = "101,102,103,104"
    VOLT_CHANNELS = "112,113,115,116,118,119"

    was_connected = False
    watchdog_timer = time.time()

    while True:
        device = None
        try:
            if not was_connected:
                log_event(f"Opening Agilent serial port {SERIAL_PORT} @ {BAUD_RATE} baud...", "INFO")

            telemetry_data["status"] = "Connecting..."
            device = serial.Serial(
                port=SERIAL_PORT, baudrate=BAUD_RATE, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, xonxoff=True,
                rtscts=False, dsrdtr=False, timeout=2.0
            )

            device.reset_input_buffer()
            device.reset_output_buffer()
            device.write(b"*CLS\r\n")
            time.sleep(0.1)
            device.write(b"*IDN?\r\n")
            time.sleep(0.1)
            idn_response = device.readline().decode("utf-8", errors="ignore").strip()

            if idn_response:
                telemetry_data["device"] = f"Device: {idn_response}"
                telemetry_data["status"] = "● Connected & Streaming"
                log_event(f"Connected: {idn_response}", "SUCCESS")
            else:
                telemetry_data["device"] = "Device: Unknown"
                telemetry_data["status"] = "● Connected (No ID)"

            was_connected = True

            while True:
                loop_start = time.time()

                # 1. HARDWARE WATCHDOG PULSE (Every 3 Seconds)
                if time.time() - watchdog_timer >= CFG["WATCHDOG_INTERVAL_SECS"]:
                    device.write(b"ROUTe:CLOSe (@201)\r\n") # Pulse 24V line
                    time.sleep(0.05)
                    device.write(b"ROUTe:OPEN (@201)\r\n")
                    watchdog_timer = time.time()
                    telemetry_data["control"]["watchdog_ok"] = True

                # 2. RUN AUTOMATED STATE MACHINE LOOP
                run_control_state_machine()

                # 3. QUERY THERMOCOUPLES (101-104)
                device.write(f"MEASure:TEMPerature? TC,T,DEF,(@{TC_CHANNELS})\r\n".encode("utf-8"))
                raw_tc = device.readline().decode("utf-8", errors="ignore").strip()
                tc_vals = parse_scpi_list(raw_tc)

                # 4. QUERY VOLTAGES (112, 113, 115, 116, 118, 119)
                device.write(f"MEASure:VOLTage:DC? AUTO,DEF,(@{VOLT_CHANNELS})\r\n".encode("utf-8"))
                raw_volt = device.readline().decode("utf-8", errors="ignore").strip()
                v_vals = parse_scpi_list(raw_volt)

                timestamp = time.strftime("%H:%M:%S")

                if len(tc_vals) >= 4:
                    telemetry_data["ch101"] = format_temp(tc_vals[0])
                    telemetry_data["ch102"] = format_temp(tc_vals[1])
                    telemetry_data["ch103"] = format_temp(tc_vals[2])
                    telemetry_data["ch104"] = format_temp(tc_vals[3])

                    telemetry_data["ch101_val"] = round(tc_vals[0], 2) if (tc_vals[0] is not None and tc_vals[0] < 9e9) else None
                    telemetry_data["ch102_val"] = round(tc_vals[1], 2) if (tc_vals[1] is not None and tc_vals[1] < 9e9) else None
                    telemetry_data["ch103_val"] = round(tc_vals[2], 2) if (tc_vals[2] is not None and tc_vals[2] < 9e9) else None
                    telemetry_data["ch104_val"] = round(tc_vals[3], 2) if (tc_vals[3] is not None and tc_vals[3] < 9e9) else None

                if len(v_vals) >= 6:
                    p_str115, p_val115 = calc_chamber_aim_sl_pressure(v_vals[2])
                    telemetry_data["ch115_v"] = f"{v_vals[2]:.3f} V" if v_vals[2] is not None else "---.-- V"
                    telemetry_data["ch115_p"] = p_str115
                    telemetry_data["ch115_p_val"] = p_val115
                    telemetry_data["ch113"] = f"{v_vals[1]:.3f} V" if v_vals[1] is not None else "---.-- V"

                    p_str116, p_val116 = calc_trap_penning_pressure(v_vals[3])
                    telemetry_data["ch116_v"] = f"{v_vals[3]:.3f} V" if v_vals[3] is not None else "---.-- V"
                    telemetry_data["ch116_p"] = p_str116
                    telemetry_data["ch116_p_val"] = p_val116
                    telemetry_data["ch112"] = f"{v_vals[0]:.3f} V" if v_vals[0] is not None else "---.-- V"

                    p_str119, p_val19 = calc_convectron_375_pressure(v_vals[5])
                    telemetry_data["ch119_v"] = f"{v_vals[5]:.3f} V" if v_vals[5] is not None else "---.-- V"
                    telemetry_data["ch119_p"] = p_str119
                    telemetry_data["ch119_p_val"] = p_val19

                telemetry_data["timestamp"] = f"Last Update: {timestamp}"
                telemetry_data["logs"] = list(system_logs)

                elapsed = time.time() - loop_start
                time.sleep(max(0.1, 1.0 - elapsed))

        except (serial.SerialException, OSError):
            if was_connected:
                log_event("Serial communication lost! Retrying in 3s...", "WARN")
                was_connected = False
            telemetry_data["status"] = "● Connection Lost! Retrying..."
            telemetry_data["device"] = "Device: Disconnected"
            if device and device.is_open:
                device.close()
            time.sleep(3.0)


@app.on_event("startup")
def startup_event():
    threading.Thread(target=serial_hardware_loop, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/control/fsm")
async def toggle_fsm(req: Request):
    """API endpoint to Start/Stop the automated state machine."""
    data = await req.json()
    enable = data.get("enable", False)
    telemetry_data["fsm"]["enabled"] = enable
    if enable:
        telemetry_data["fsm"]["state"] = "START_COOLING_A"
        telemetry_data["fsm"]["timer_secs"] = 0
        log_event("Automated State Machine STARTED by user.", "SUCCESS")
    else:
        telemetry_data["fsm"]["state"] = "IDLE"
        log_event("Automated State Machine STOPPED by user.", "WARN")
    return JSONResponse({"status": "ok", "enabled": enable})


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(telemetry_data)
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, Exception):
        pass