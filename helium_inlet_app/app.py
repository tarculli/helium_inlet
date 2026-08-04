import asyncio
import math
import threading
import time
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import serial

app = FastAPI(title="Helium Inlet Control System")
templates = Jinja2Templates(directory="templates")

# --- LOG MANAGEMENT ---
MAX_LOG_ENTRIES = 50
system_logs = []


def log_event(message: str, level: str = "INFO"):
    """Appends a timestamped log entry to the event queue."""
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "level": level, "msg": message}
    system_logs.append(entry)
    if len(system_logs) > MAX_LOG_ENTRIES:
        system_logs.pop(0)


# Initialize startup log
log_event("Control hub initialized. Telemetry thread starting...", "INFO")

# --- GLOBAL TELEMETRY STATE ---
telemetry_data = {
    "status": "Initializing...",
    "device": "Disconnected",
    "timestamp": "Waiting for data...",
    "logs": system_logs,
    # Engine A
    "ch104": "---.-- °C",
    "ch104_val": None,
    "ch103": "---.-- °C",
    "ch103_val": None,
    # Engine B
    "ch101": "---.-- °C",
    "ch101_val": None,
    "ch102": "---.-- °C",
    "ch102_val": None,
    # Chamber
    "ch115_p": "---.--- Torr",
    "ch115_p_val": None,
    "ch115_v": "---.-- V",
    "ch113": "---.-- V",
    # Trap
    "ch116_p": "---.--- Torr",
    "ch116_p_val": None,
    "ch116_v": "---.-- V",
    "ch112": "---.-- V",
    # Convectrons
    "ch118_p": "N/A",
    "ch118_p_val": None,
    "ch118_v": "N/A",
    "ch119_p": "---.--- Torr",
    "ch119_p_val": None,
    "ch119_v": "---.-- V",
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
    """Formats Type-T TC temperature or checks for open circuit (~9.9E37)."""
    if val is None:
        return "---.-- °C"
    if val > 9e9:
        return "OPEN / NC"
    return f"{val:.1f} °C"


# --- PRESSURE CONVERSION FUNCTIONS (TORR) ---

def calc_trap_penning_pressure(volts):
    """Calculates Trap Penning B pressure in Torr."""
    if volts is None:
        return "---.--- Torr", None
    try:
        pressure_mbar = 10 ** ((volts * 0.875) - 10.75)
        pressure_torr = pressure_mbar * 0.750062
        return f"{pressure_torr:.2e} Torr", pressure_torr
    except Exception:
        return "Error", None


def calc_chamber_aim_sl_pressure(volts):
    """
    Calculates Chamber pressure for Edwards AIM-SL Gauge in Torr based on Table 2 characteristics.
    Uses log-linear interpolation between known voltage points.
    """
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
    """
    Calculates Convectron pressure for GP 375 Controller (0-7V Log-Linear setting).
    Equation: P = 10^(V - 4) Torr
    """
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


# --- BACKGROUND HARDWARE WORKER (1s LOOP) ---
def serial_hardware_loop():
    """Continuous background thread querying Agilent 34970A channels every 1.0s."""
    global telemetry_data

    SERIAL_PORT = "/dev/ttyUSB0"
    BAUD_RATE = 57600

    TC_CHANNELS = "101,102,103,104"
    VOLT_CHANNELS = "112,113,115,116,118,119"

    was_connected = False

    while True:
        device = None
        try:
            if not was_connected:
                log_event(f"Opening serial port {SERIAL_PORT} @ {BAUD_RATE} baud...", "INFO")

            telemetry_data["status"] = "Connecting..."

            device = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD_RATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=True,
                rtscts=False,
                dsrdtr=False,
                timeout=2.0,
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
                log_event("Started 1.0s SCPI hardware polling cycle.", "INFO")
            else:
                telemetry_data["device"] = "Device: Unknown"
                telemetry_data["status"] = "● Connected (No ID)"
                log_event("Serial port opened, but hardware did not respond to *IDN?.", "WARN")

            was_connected = True

            # Main Polling Loop
            while True:
                loop_start = time.time()

                # 1. Query Thermocouples (101-104)
                device.write(f"MEASure:TEMPerature? TC,T,DEF,(@{TC_CHANNELS})\r\n".encode("utf-8"))
                raw_tc = device.readline().decode("utf-8", errors="ignore").strip()
                tc_vals = parse_scpi_list(raw_tc)

                # 2. Query Voltages (112, 113, 115, 116, 118, 119)
                device.write(f"MEASure:VOLTage:DC? AUTO,DEF,(@{VOLT_CHANNELS})\r\n".encode("utf-8"))
                raw_volt = device.readline().decode("utf-8", errors="ignore").strip()
                v_vals = parse_scpi_list(raw_volt)

                timestamp = time.strftime("%H:%M:%S")

                # Update Thermocouples
                if len(tc_vals) >= 4:
                    telemetry_data["ch101"] = format_temp(tc_vals[0])
                    telemetry_data["ch102"] = format_temp(tc_vals[1])
                    telemetry_data["ch103"] = format_temp(tc_vals[2])
                    telemetry_data["ch104"] = format_temp(tc_vals[3])

                    telemetry_data["ch101_val"] = round(tc_vals[0], 2) if (tc_vals[0] is not None and tc_vals[0] < 9e9) else None
                    telemetry_data["ch102_val"] = round(tc_vals[1], 2) if (tc_vals[1] is not None and tc_vals[1] < 9e9) else None
                    telemetry_data["ch103_val"] = round(tc_vals[2], 2) if (tc_vals[2] is not None and tc_vals[2] < 9e9) else None
                    telemetry_data["ch104_val"] = round(tc_vals[3], 2) if (tc_vals[3] is not None and tc_vals[3] < 9e9) else None

                # Update Voltages & Pressures (Torr)
                if len(v_vals) >= 6:
                    # Chamber (CH 115)
                    p_str, p_val = calc_chamber_aim_sl_pressure(v_vals[2])
                    telemetry_data["ch115_v"] = f"{v_vals[2]:.3f} V" if v_vals[2] is not None else "---.-- V"
                    telemetry_data["ch115_p"] = p_str
                    telemetry_data["ch115_p_val"] = p_val
                    telemetry_data["ch113"] = f"{v_vals[1]:.3f} V" if v_vals[1] is not None else "---.-- V"

                    # Trap (CH 116)
                    p_str, p_val = calc_trap_penning_pressure(v_vals[3])
                    telemetry_data["ch116_v"] = f"{v_vals[3]:.3f} V" if v_vals[3] is not None else "---.-- V"
                    telemetry_data["ch116_p"] = p_str
                    telemetry_data["ch116_p_val"] = p_val
                    telemetry_data["ch112"] = f"{v_vals[0]:.3f} V" if v_vals[0] is not None else "---.-- V"

                    # Convectron - Ignored CH 118 (v_vals[4]) for now
                    telemetry_data["ch118_v"] = "N/A"
                    telemetry_data["ch118_p"] = "N/A (Unconnected)"
                    telemetry_data["ch118_p_val"] = None

                    # Convectron - Active CH 119 (v_vals[5])
                    p_str19, p_val19 = calc_convectron_375_pressure(v_vals[5])
                    telemetry_data["ch119_v"] = f"{v_vals[5]:.3f} V" if v_vals[5] is not None else "---.-- V"
                    telemetry_data["ch119_p"] = p_str19
                    telemetry_data["ch119_p_val"] = p_val19

                telemetry_data["timestamp"] = f"Last Update: {timestamp}"
                telemetry_data["logs"] = list(system_logs)

                # Maintain 1.0s loop timing
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


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(telemetry_data)
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, Exception):
        pass