import asyncio
import json
import math
import threading
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import serial

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- GLOBAL SHARED DATA STATE ---
# Hardware thread writes to this; WebSockets read from this.
latest_data = {
    "pressure": "---.--- mbar",
    "temp": "---.-- °C",
    "status": "● Initializing...",
    "status_color": "orange",
    "idn": "Device: Disconnected",
    "timestamp": "--:--:--",
}
data_lock = threading.Lock()


# --- BACKGROUND HARDWARE THREAD ---
def serial_hardware_worker():
    global latest_data

    SERIAL_PORT = "/dev/ttyUSB0"
    BAUD_RATE = 57600
    TC_CHANNEL = "102"
    TC_TYPE = "T"
    VOLT_CHANNEL = "116"

    while True:
        device = None
        try:
            with data_lock:
                latest_data["status"] = "● Connecting to hardware..."
                latest_data["status_color"] = "orange"

            device = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD_RATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=True,
                rtscts=False,
                dsrdtr=False,
                timeout=3.0,
            )

            device.reset_input_buffer()
            device.reset_output_buffer()

            device.write(b"*CLS\r\n")
            time.sleep(0.1)

            device.write(b"*IDN?\r\n")
            time.sleep(0.2)
            idn_response = device.readline().decode("utf-8", errors="ignore").strip()

            with data_lock:
                if idn_response:
                    latest_data["idn"] = f"Device: {idn_response}"
                    latest_data["status"] = "● Connected & Streaming"
                    latest_data["status_color"] = "#2ea043"  # Green
                else:
                    latest_data["idn"] = "Device: Unknown"
                    latest_data["status"] = "● Connected (No ID response)"
                    latest_data["status_color"] = "orange"

            # Active streaming loop
            while True:
                # 1. Query Channel 116 Voltage
                device.write(f"MEASure:VOLTage:DC? AUTO,DEF,(@{VOLT_CHANNEL})\r\n".encode("utf-8"))
                raw_volt = device.readline().decode("utf-8", errors="ignore").strip()

                # 2. Query Channel 102 Temperature
                device.write(f"MEASure:TEMPerature? TC,{TC_TYPE},DEF,(@{TC_CHANNEL})\r\n".encode("utf-8"))
                raw_temp = device.readline().decode("utf-8", errors="ignore").strip()

                timestamp = time.strftime("%H:%M:%S")

                # Parse Pressure
                p_str = "---.--- mbar"
                if raw_volt:
                    try:
                        volts = float(raw_volt)
                        pressure_mbar = 10 ** ((volts * 0.875) - 10.75)
                        p_str = f"{pressure_mbar:.2e} mbar"
                    except ValueError:
                        p_str = f"{raw_volt} mbar"

                # Parse Temperature
                t_c_str = "---.-- °C"
                if raw_temp:
                    try:
                        temp_c = float(raw_temp)
                        if temp_c > 9e9:
                            t_c_str = "OPEN / NC"
                        else:
                            t_c_str = f"{temp_c:.2f} °C"
                    except ValueError:
                        t_c_str = f"{raw_temp}"

                # Update global state thread-safely
                with data_lock:
                    latest_data["pressure"] = p_str
                    latest_data["temp"] = t_c_str
                    latest_data["timestamp"] = timestamp

                time.sleep(1.5)

        except (serial.SerialException, OSError):
            with data_lock:
                latest_data["status"] = "● Connection Lost! Retrying in 5s..."
                latest_data["status_color"] = "#f85149"  # Red
                latest_data["pressure"] = "---.--- mbar"
                latest_data["temp"] = "---.-- °C"
                latest_data["idn"] = "Device: Disconnected"

            if device and device.is_open:
                device.close()

            time.sleep(5.0)


# Start hardware background thread on server startup
@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=serial_hardware_worker, daemon=True)
    thread.start()


# --- WEBPAGE ROUTE ---
@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# --- WEBSOCKET STREAMING ENDPOINT ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Read shared data state safely and push to web client
            with data_lock:
                payload = json.dumps(latest_data)

            await websocket.send_text(payload)
            await asyncio.sleep(1.0)  # Push frequency to browser
    except WebSocketDisconnect:
        pass