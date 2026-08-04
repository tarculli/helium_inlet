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
    "ch115_p": "Pending Table",
    "ch115_p_val": None,  # Raw numeric for plotting
    "ch115_v": "---.-- V",
    "ch113": "---.-- V",
    # Trap
    "ch116_p": "---.--- mbar",
    "ch116_p_val": None,  # Raw numeric for plotting
    "ch116_v": "---.-- V",
    "ch112": "---.-- V",
    # Convectrons
    "ch118_p": "Pending Table",
    "ch118_v": "---.-- V",
    "ch119_p": "Pending Table",
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


def calc_aim_sl_pressure(volts):
    """Calculates Chamber pressure (mbar) for Edwards AIM-SL Gauge (returns float)."""
    if volts is None or volts < 2.00: return 1.0e-8
    if volts > 10.00: return 1.0e-2

    aim_sl_table = [
        (2.00, 1.0e-8), (2.50, 2.4e-8), (3.00, 5.8e-8), (3.20, 8.1e-8),
        (3.40, 1.1e-7), (3.60, 1.5e-7), (3.80, 2.1e-7), (4.00, 2.9e-7),
        (4.20, 4.0e-7), (4.40, 5.4e-7), (4.60, 7.3e-7), (4.80, 9.8e-7),
        (5.00, 1.3e-6), (5.20, 1.7e-6), (5.40, 2.2e-6), (5.60, 2.8e-6),
        (5.80, 3.6e-6), (6.00, 4.5e-6), (6.20, 5.6e-6), (6.40, 6.9e-6),
        (6.60, 8.4e-6), (6.80, 1.0e-5), (7.00, 1.2e-5), (7.20, 1.4e-5),
        (7.40, 1.7e-5), (7.60, 2.0e-5), (7.80, 2.4e-5), (8.00, 2.9e-5),
        (8.20, 3.5e-5), (8.40, 4.3e-5), (8.60, 5.7e-5), (8.80, 7.9e-5),
        (9.00, 1.2e-4), (9.20, 1.9e-4), (9.40, 3.3e-4), (9.60, 6.7e-4),
        (9.80, 1.7e-3), (9.90, 3.6e-3), (10.00, 1.0e-2)
    ]

    for v, p in aim_sl_table:
        if abs(volts - v) < 0.001:
            return p

    for i in range(len(aim_sl_table) - 1):
        v1, p1 = aim_sl_table[i]
        v2, p2 = aim_sl_table[i+1]
        
        if v1 < volts < v2:
            log_p1 = math.log10(p1)
            log_p2 = math.log10(p2)
            log_p = log_p1 + (volts - v1) * ((log_p2 - log_p1) / (v2 - v1))
            return 10 ** log_p
    return 1.0e-8


def calc_trap_penning_pressure(volts):
    """Calculates Trap Penning B pressure (returns float)."""
    if volts is None: return 1.0e-8
    try:
        return 10 ** ((volts * 0.875) - 10.75)
    except Exception:
        return 1.0e-8


# --- BACKGROUND HARDWARE WORKER (1s LOOP) ---
def serial_hardware_loop():
    """Continuous background thread querying all Agilent 34970A channels every 1.0s."""
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

                    # Raw numeric floats for chart
                    telemetry_data["ch101_val"] = round(tc_vals[0], 2) if (tc_vals[0] is not None and tc_vals[0] < 9e9) else None
                    telemetry_data["ch102_val"] = round(tc_vals[1], 2) if (tc_vals[1] is not None and tc_vals[1] < 9e9) else None
                    telemetry_data["ch103_val"] = round(tc_vals[2], 2) if (tc_vals[2] is not None and tc_vals[2] < 9e9) else None
                    telemetry_data["ch104_val"] = round(tc_vals[3], 2) if (tc_vals[3] is not None and tc_vals[3] < 9e9) else None

                # Update Voltages & Pressures
                if len(v_vals) >= 6:
                    
                    # Chamber (Index 2 is CH 115)
                    v115 = v_vals[2]
                    if v115 is not None:
                        p115_val = calc_aim_sl_pressure(v115)
                        telemetry_data["ch115_p_val"] = p115_val
                        telemetry_data["ch115_p"] = f"{p115_val:.2e} mbar"
                        telemetry_data["ch115_v"] = f"{v115:.3f} V"
                    else:
                        telemetry_data["ch115_p_val"] = None
                        telemetry_data["ch115_p"] = "---.--- mbar"
                        telemetry_data["ch115_v"] = "---.-- V"

                    telemetry_data["ch113"] = f"{v_vals[1]:.3f} V" if v_vals[1] is not None else "---.-- V"

                    # Trap (Index 3 is CH 116)
                    v116 = v_vals[3]
                    if v116 is not None:
                        p116_val = calc_trap_penning_pressure(v116)
                        telemetry_data["ch116_p_val"] = p116_val
                        telemetry_data["ch116_p"] = f"{p116_val:.2e} mbar"
                        telemetry_data["ch116_v"] = f"{v116:.3f} V"
                    else:
                        telemetry_data["ch116_p_val"] = None
                        telemetry_data["ch116_p"] = "---.--- mbar"
                        telemetry_data["ch116_v"] = "---.-- V"

                    telemetry_data["ch112"] = f"{v_vals[0]:.3f} V" if v_vals[0] is not None else "---.-- V"

                    # Convectrons (Index 4 is CH 118, Index 5 is CH 119)
                    telemetry_data["ch118_v"] = f"{v_vals[4]:.3f} V" if v_vals[4] is not None else "---.-- V"
                    telemetry_data["ch118_p"] = "Pending Table"
                    
                    telemetry_data["ch119_v"] = f"{v_vals[5]:.3f} V" if v_vals[5] is not None else "---.-- V"
                    telemetry_data["ch119_p"] = "Pending Table"

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
            
            # Clear plotting values
            telemetry_data["ch115_p_val"] = None
            telemetry_data["ch116_p_val"] = None

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
        pass  # Quiet disconnects