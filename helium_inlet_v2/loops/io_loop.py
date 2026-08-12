import time
from hardware.agilent import Agilent34970A
import state
from config import IO_POLL_RATE_SEC

def format_temp(val):
    if val is None: return "---.-- °C"
    return f"{val:.2f} °C"

def format_pressure(volts):
    if volts is None or volts < 0.5: return None, "---.--- Torr"
    # Formula matching your original Agilent calculations
    p_val = 10 ** (volts - 10.0) 
    return p_val, f"{p_val:.2e} Torr"

def format_voltage(volts):
    if volts is None: return "---.-- V"
    return f"{volts:.2f} V"

def run_io_loop():
    agilent = Agilent34970A()
    state.log_event("Starting IO Loop...", "INFO")

    while True:
        loop_start = time.time()

        # 1. Connection Management
        if not agilent.connected:
            state.telemetry_data["status"] = "Connecting..."
            idn = agilent.connect()
            
            if idn:
                state.telemetry_data["device"] = f"Device: {idn}"
                state.telemetry_data["status"] = "● Connected & Streaming"
                state.log_event("Agilent connected.", "SUCCESS")
            else:
                state.telemetry_data["status"] = "● Connection Lost! Retrying..."
                time.sleep(3.0)
                continue
        else:
            # 2. Hardware Acquisition
            tc_vals, v_vals = agilent.read_all()
            if not tc_vals or not v_vals:
                state.log_event("Lost connection to Agilent.", "WARN")
                agilent.connected = False
                continue

        # 3. Data Mapping & Formatting
        # --- MAP TEMPERATURES (Assuming order: 101, 102, 103, 104) ---
        if tc_vals and len(tc_vals) >= 4:
            state.telemetry_data["ch101_val"] = tc_vals[0]
            state.telemetry_data["ch101"] = format_temp(tc_vals[0])
            state.telemetry_data["ch102_val"] = tc_vals[1]
            state.telemetry_data["ch102"] = format_temp(tc_vals[1])
            state.telemetry_data["ch103_val"] = tc_vals[2]
            state.telemetry_data["ch103"] = format_temp(tc_vals[2])
            state.telemetry_data["ch104_val"] = tc_vals[3]
            state.telemetry_data["ch104"] = format_temp(tc_vals[3])

        # --- MAP VOLTAGES & PRESSURES (Assuming order: 112, 113, 115, 116, 118, 119) ---
        if v_vals and len(v_vals) >= 6:
            state.telemetry_data["ch112"] = format_voltage(v_vals[0])
            state.telemetry_data["ch113"] = format_voltage(v_vals[1])
            
            p115, p115_str = format_pressure(v_vals[2])
            state.telemetry_data["ch115_p_val"] = p115
            state.telemetry_data["ch115_p"] = p115_str
            state.telemetry_data["ch115_v"] = format_voltage(v_vals[2])
            
            p116, p116_str = format_pressure(v_vals[3])
            state.telemetry_data["ch116_p_val"] = p116
            state.telemetry_data["ch116_p"] = p116_str
            state.telemetry_data["ch116_v"] = format_voltage(v_vals[3])
            
            state.telemetry_data["ch118_v"] = format_voltage(v_vals[4])
            
            p119, p119_str = format_pressure(v_vals[5])
            state.telemetry_data["ch119_p_val"] = p119
            state.telemetry_data["ch119_p"] = p119_str
            state.telemetry_data["ch119_v"] = format_voltage(v_vals[5])

        # 4. Metadata Update
        state.telemetry_data["timestamp"] = f"Last Update: {time.strftime('%H:%M:%S')}"
        state.telemetry_data["logs"] = list(state.system_logs)

        # 5. Timing Enforcement
        elapsed = time.time() - loop_start
        time.sleep(max(0.01, IO_POLL_RATE_SEC - elapsed))