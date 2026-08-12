import time
from hardware.agilent import Agilent34970A
import state
from config import IO_POLL_RATE_SEC

def run_io_loop():
    agilent = Agilent34970A()
    state.log_event("Starting IO Loop...", "INFO")

    while True:
        loop_start = time.time()

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

        # Execute commands from queue (Future)
        while not state.command_queue.empty():
            cmd = state.command_queue.get()
            # Process command here...

        # Read sensors
        tc_vals, v_vals = agilent.read_all()
        
        if tc_vals and len(tc_vals) >= 4:
            # Map tc_vals to state.telemetry_data["ch101"], etc.
            pass
            
        if v_vals and len(v_vals) >= 6:
            # Map v_vals through agilent calculation methods into state.telemetry_data
            pass

        state.telemetry_data["timestamp"] = f"Last Update: {time.strftime('%H:%M:%S')}"
        state.telemetry_data["logs"] = list(state.system_logs)

        # Enforce loop timing
        elapsed = time.time() - loop_start
        time.sleep(max(0.01, IO_POLL_RATE_SEC - elapsed))