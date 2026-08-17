'''
This script handles the telemetry loop based on the data stream (temperature, pressure) 
coming from the Agilent 34970A.
'''

import time

# Importing local scripts, functions from /helium_inlet_v2/
from hardware.agilent import Agilent34970A
import state
from config import IO_POLL_RATE_SEC

def run_io_loop():
    agilent = Agilent34970A()
    state.log_event("Starting IO Loop...", "INFO")

    while True:
        loop_start = time.time()
        # Safety initialization so variables always exist
        tc_vals, v_vals = None, None 

        # 1. Connection Management
        if not agilent.connected:
            state.telemetry_data["status"] = "Connecting..."
            idn = agilent.connect()
            if idn:
                state.telemetry_data["device"] = f"Device: {idn}"
                state.telemetry_data["status"] = "● Connected & Streaming"
                state.log_event("Agilent connected.", "SUCCESS")
                # Skip the rest of this cycle so we can read data on the next one
                continue 
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
            state.telemetry_data["ch101"] = Agilent34970A.format_temp(tc_vals[0])
            
            state.telemetry_data["ch102_val"] = tc_vals[1]
            state.telemetry_data["ch102"] = Agilent34970A.format_temp(tc_vals[1])
            
            state.telemetry_data["ch103_val"] = tc_vals[2]
            state.telemetry_data["ch103"] = Agilent34970A.format_temp(tc_vals[2])
            
            state.telemetry_data["ch104_val"] = tc_vals[3]
            state.telemetry_data["ch104"] = Agilent34970A.format_temp(tc_vals[3])

        # --- MAP VOLTAGES & PRESSURES (Assuming order: 112, 113, 115, 116, 118, 119) ---
        if v_vals and len(v_vals) >= 6:
            # Turbos
            state.telemetry_data["ch112"] = Agilent34970A.format_voltage(v_vals[0])
            state.telemetry_data["ch113"] = Agilent34970A.format_voltage(v_vals[1])
            
            # Chamber AIM-SL Gauge (115)
            p115, p115_str = Agilent34970A.calc_chamber_aim_sl_pressure(v_vals[2])
            state.telemetry_data["ch115_p_val"] = p115
            state.telemetry_data["ch115_p"] = p115_str
            state.telemetry_data["ch115_v"] = Agilent34970A.format_voltage(v_vals[2])
            
            # Trap Penning Gauge (116)
            p116, p116_str = Agilent34970A.calc_trap_penning_pressure(v_vals[3])
            state.telemetry_data["ch116_p_val"] = p116
            state.telemetry_data["ch116_p"] = p116_str
            state.telemetry_data["ch116_v"] = Agilent34970A.format_voltage(v_vals[3])
            
            # Unconnected HiVac (118)
            state.telemetry_data["ch118_v"] = Agilent34970A.format_voltage(v_vals[4])
            
            # Trap LoVac Convectron (119)
            p119, p119_str = Agilent34970A.calc_convectron_375_pressure(v_vals[5])
            state.telemetry_data["ch119_p_val"] = p119
            state.telemetry_data["ch119_p"] = p119_str
            state.telemetry_data["ch119_v"] = Agilent34970A.format_voltage(v_vals[5])

        # 4. Metadata Update
        state.telemetry_data["timestamp"] = f"Last Update: {time.strftime('%H:%M:%S')}"
        state.telemetry_data["logs"] = list(state.system_logs)

        # 5. Timing Enforcement
        elapsed = time.time() - loop_start
        time.sleep(max(0.01, IO_POLL_RATE_SEC - elapsed))