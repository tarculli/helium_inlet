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
    """Appends a new system event log with a timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "level": level, "msg": message}
    system_logs.append(entry)
    if len(system_logs) > MAX_LOG_ENTRIES:
        system_logs.pop(0)


# Initialize starting log
log_event("System initialized. Background workers starting...", "INFO")

# --- GLOBAL TELEMETRY STATE ---
telemetry_data = {
    "status": "Initializing...",
    "device": "Disconnected",
    "timestamp": "Waiting for data...",
    "logs": system_logs,
    # Engine A
    "ch104": "---.-- °C",
    "ch103": "---.-- °C",
    # Engine B
    "ch101": "---.-- °C",
    "ch102": "---.-- °C",
    # Chamber
    "ch115_p": "Pending Table",
    "ch115_v": "---.-- V",
    "ch113": "---.-- V",
    # Trap
    "ch116_p": "---.--- mbar",
    "ch116_v": "---.-- V",
    "ch112": "---.-- V",
    # Convectrons
    "ch118_p": "Pending Table",
    "ch118_v": "---.-- V",
    "ch119_p": "Pending Table",
    "ch119_v": "---.-- V",
}


def parse_scpi_list(raw_response: str):
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
    if val > 9e9:  # Agilent open thermocouple indicator
        return "OPEN / NC"
    return f"{val:.1f} °C"


def calc_trap_penning_pressure(volts):
    if volts is None:
        return "---.--- mbar"
    try:
        pressure_mbar = 10 ** ((volts * 0.875) - 10.75)
        return f"{pressure_mbar:.2e} mbar"
    except Exception:
        return "Error"


# --- BACKGROUND HARDWARE WORKER (1s LOOP) ---
def serial_hardware_loop():
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
                log_event(f"Attempting connection to {SERIAL_PORT} @ {BAUD_RATE} baud...", "INFO")

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
                log_event("Started 1.0s telemetry streaming cycle.", "INFO")
            else:
                telemetry_data["device"] = "Device: Unknown"
                telemetry_data["status"] = "● Connected (No ID)"
                log_event("Connected to serial port, but no SCPI *IDN? response.", "WARN")

            was_connected = True

            # Main Polling Loop
            while True:
                loop_start = time.time()

                # Query Thermocouples
                device.write(f"MEASure:TEMPerature? TC,T,DEF,(@{TC_CHANNELS})\r\n".encode("utf-8"))
                raw_tc = device.readline().decode("utf-8", errors="ignore").strip()
                tc_vals = parse_scpi_list(raw_tc)

                # Query Voltages
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

                # Update Voltages & Pressures
                if len(v_vals) >= 6:
                    # Chamber
                    telemetry_data["ch115_v"] = f"{v_vals[2]:.3f} V" if v_vals[2] is not None else "---.-- V"
                    telemetry_data["ch115_p"] = "Pending Table"
                    telemetry_data["ch113"]   = f"{v_vals[1]:.3f} V" if v_vals[1] is not None else "---.-- V"

                    # Trap
                    telemetry_data["ch116_v"] = f"{v_vals[3]:.3f} V" if v_vals[3] is not None else "---.-- V"
                    telemetry_data["ch116_p"] = calc_trap_penning_pressure(v_vals[3])
                    telemetry_data["ch112"]   = f"{v_vals[0]:.3f} V" if v_vals[0] is not None else "---.-- V"

                    # Convectrons
                    telemetry_data["ch118_v"] = f"{v_vals[4]:.3f} V" if v_vals[4] is not None else "---.-- V"
                    telemetry_data["ch118_p"] = "Pending Table"
                    telemetry_data["ch119_v"] = f"{v_vals[5]:.3f} V" if v_vals[5] is not None else "---.-- V"
                    telemetry_data["ch119_p"] = "Pending Table"

                telemetry_data["timestamp"] = f"Last Update: {timestamp}"
                telemetry_data["logs"] = system_logs

                elapsed = time.time() - loop_start
                sleep_time = max(0.1, 1.0 - elapsed)
                time.sleep(sleep_time)

        except (serial.SerialException, OSError) as e:
            if was_connected:
                log_event("Serial communication lost! Retrying...", "WARN")
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
    except WebSocketDisconnect:
        print("Client disconnected from telemetry feed.")