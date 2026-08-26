import time
import state

FLOW_STATES = [1, 2, 3, 4, 0]
STEP_INTERVAL_SEC = 5.0

def run_auto_loop():
    state.log_event("Automated Sequence thread initialized.", "INFO")
    current_idx = 0

    while True:
        # Check if system is active in automatic mode
        if state.telemetry_data.get("mode") == "AUTOMATIC ACQUISITION":
            target_state = FLOW_STATES[current_idx]
            
            # Dispatch command through thread-safe queue
            state.enqueue_command({"cmd": "SET_FLOW_STATE", "state": target_state})
            
            # Advance to next state index for future iteration
            current_idx = (current_idx + 1) % len(FLOW_STATES)

            # Responsive 5-second wait interval
            start_time = time.time()
            while time.time() - start_time < STEP_INTERVAL_SEC:
                time.sleep(0.1)
                # Break delay immediately if mode is toggled off or ESTOP triggers
                if state.telemetry_data.get("mode") != "AUTOMATIC ACQUISITION":
                    current_idx = 0
                    break
        else:
            current_idx = 0
            time.sleep(0.5)