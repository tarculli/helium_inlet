"""
This script handles the telemetry loop based on the data stream (temperature, pressure) 
coming from the Agilent 34970A and processes pending hardware control commands.
"""

import logging
import time
import state
from config import IO_POLL_RATE_SEC
from hardware.agilent import Agilent34970A

logger = logging.getLogger(__name__)


def run_io_loop():
    """Main execution thread for hardware communications.

    Manages connection lifecycle, polls physical sensors, processes hardware
    commands from state.py, and updates global telemetry dictionary.
    """
    agilent = Agilent34970A()
    state.log_event("IO Loop thread started.", "INFO")

    while getattr(state, "is_running", True):
        loop_start = time.time()

        try:
            # ==============================================================================
            # 1. HARDWARE CONNECTION MANAGEMENT
            # ==============================================================================
            if not agilent.connected:
                state.update_telemetry({"status": "CONNECTING..."})
                idn = agilent.connect()
                if idn:
                    state.update_telemetry(
                        {"device": f"Device: {idn}", "status": "CONNECTED"}
                    )
                    state.log_event("Connected to Agilent mainframe.", "SUCCESS")
                else:
                    state.update_telemetry({"status": "DISCONNECTED"})
                    time.sleep(2.0)
                    continue

            # ==============================================================================
            # 2. PROCESS QUEUED CONTROL COMMANDS
            # ==============================================================================
            state.process_command_queue(agilent)

            # ==============================================================================
            # 3. POLL HARDWARE SENSORS
            # ==============================================================================
            tc_vals, v_vals = agilent.read_all()

            if tc_vals is None or v_vals is None:
                state.log_event(
                    "Serial read timeout. Resetting connection...", "WARN"
                )
                agilent.connected = False
                continue

            # Accumulator dictionary for atomic telemetry updates
            updates = {}

            # ==============================================================================
            # 4. MAP THERMOCOUPLE DATA (Channels 101-104)
            # ==============================================================================
            if len(tc_vals) >= 4:
                # 9.9E+37 is Agilent default for open circuit / overload
                updates["ch101_val"] = tc_vals[0] if tc_vals[0] < 9e9 else None
                updates["ch102_val"] = tc_vals[1] if tc_vals[1] < 9e9 else None
                updates["ch103_val"] = tc_vals[2] if tc_vals[2] < 9e9 else None
                updates["ch104_val"] = tc_vals[3] if tc_vals[3] < 9e9 else None

                updates["ch101"] = Agilent34970A.format_temp(tc_vals[0])
                updates["ch102"] = Agilent34970A.format_temp(tc_vals[1])
                updates["ch103"] = Agilent34970A.format_temp(tc_vals[2])
                updates["ch104"] = Agilent34970A.format_temp(tc_vals[3])

            # ==============================================================================
            # 5. MAP VOLTAGES & CALCULATED VACUUM PRESSURES
            # ==============================================================================
            if len(v_vals) >= 6:
                updates["ch112"] = Agilent34970A.format_voltage(v_vals[0])
                updates["ch113"] = Agilent34970A.format_voltage(v_vals[1])

                # Chamber AIM-SL Gauge (Channel 115)
                p115, p115_str = Agilent34970A.calc_chamber_aim_sl_pressure(
                    v_vals[2]
                )
                updates["ch115_p_val"] = p115
                updates["ch115_p"] = p115_str
                updates["ch115_v"] = Agilent34970A.format_voltage(v_vals[2])

                # Trap Penning Gauge (Channel 116)
                p116, p116_str = Agilent34970A.calc_trap_penning_pressure(
                    v_vals[3]
                )
                updates["ch116_p_val"] = p116
                updates["ch116_p"] = p116_str
                updates["ch116_v"] = Agilent34970A.format_voltage(v_vals[3])

                # Spare Analog Channel (Channel 118)
                updates["ch118_v"] = Agilent34970A.format_voltage(v_vals[4])

                # Trap LoVac Convectron Gauge (Channel 119)
                p119, p119_str = Agilent34970A.calc_convectron_375_pressure(
                    v_vals[5]
                )
                updates["ch119_p_val"] = p119
                updates["ch119_p"] = p119_str
                updates["ch119_v"] = Agilent34970A.format_voltage(v_vals[5])

            # ==============================================================================
            # 6. METADATA & BATCH STATE UPDATE
            # ==============================================================================
            now_str = time.strftime("%H:%M:%S")
            updates["time_str"] = now_str
            updates["timestamp"] = f"Last Update: {now_str}"

            # Apply atomic state update
            state.update_telemetry(updates)

        except Exception as e:
            logger.error(f"Unhandled exception in IO loop: {e}", exc_info=True)
            state.log_event(f"Hardware loop error: {str(e)}", "DANGER")
            agilent.connected = False
            time.sleep(1.0)

        # ==============================================================================
        # 7. DYNAMIC LOOP THROTTLING
        # ==============================================================================
        elapsed = time.time() - loop_start
        time.sleep(max(0.05, IO_POLL_RATE_SEC - elapsed))

    state.log_event("IO Loop thread stopped.", "WARN")