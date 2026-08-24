'''
This script handles the telemetry loop based on the data stream (temperature, pressure) 
coming from the Agilent 34970A and processes pending hardware control commands.
'''

import time
from hardware.agilent import Agilent34970A
import state
from config import IO_POLL_RATE_SEC

def run_io_loop():
    agilent = Agilent34970A()
    state.log_event("IO Loop thread started.", "INFO")

    while True:
        loop_start = time.time()

        # 1. Connection check
        if not agilent.connected:
            state.telemetry_data["status"] = "Connecting..."
            idn = agilent.connect()
            if idn:
                state.telemetry_data["device"] = f"Device: {idn}"
                state.telemetry_data["status"] = "CONNECTED"
                state.log_event("Connected to Agilent mainframe.", "SUCCESS")
            else:
                state.telemetry_data["status"] = "DISCONNECTED"
                time.sleep(2.0)
                continue

        # 2. Process incoming commands from UI before reading sensors
        state.process_command_queue(agilent)

        # 3. Read sensors
        tc_vals, v_vals = agilent.read_all()
        if tc_vals is None or v_vals is None:
            state.log_event("Serial read timeout. Resetting connection...", "WARN")
            agilent.connected = False
            continue

        # 4. Map Telemetry
        # --- MAP TEMPERATURES (101, 102, 103, 104) ---
        if tc_vals and len(tc_vals) >= 4:
            # Raw numeric floats for JS plotting engine (filters out open thermocouple fault values)
            state.telemetry_data["ch101_val"] = tc_vals[0] if tc_vals[0] < 9e9 else None
            state.telemetry_data["ch102_val"] = tc_vals[1] if tc_vals[1] < 9e9 else None
            state.telemetry_data["ch103_val"] = tc_vals[2] if tc_vals[2] < 9e9 else None
            state.telemetry_data["ch104_val"] = tc_vals[3] if tc_vals[3] < 9e9 else None

            # Formatted string text for dashboard cards
            state.telemetry_data["ch101"] = Agilent34970A.format_temp(tc_vals[0])
            state.telemetry_data["ch102"] = Agilent34970A.format_temp(tc_vals[1])
            state.telemetry_data["ch103"] = Agilent34970A.format_temp(tc_vals[2])
            state.telemetry_data["ch104"] = Agilent34970A.format_temp(tc_vals[3])

        # --- MAP VOLTAGES & PRESSURES (112, 113, 115, 116, 118, 119) ---
        if v_vals and len(v_vals) >= 6:
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

# 5. Metadata Update
        now_str = time.strftime('%H:%M:%S')
        state.telemetry_data["time_str"] = now_str
        state.telemetry_data["timestamp"] = f"Last Update: {now_str}"
        state.telemetry_data["logs"] = list(state.system_logs)