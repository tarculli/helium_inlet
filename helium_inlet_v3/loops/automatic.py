"""
loops/automatic.py - Automated Sequence Engine

This module executes automated, time-based valve state sequences. It runs as a 
background daemon thread, monitoring the global system mode in state.py. 
When set to "AUTOMATIC ACQUISITION", it steps through predefined flow states 
by dispatching commands into state.command_queue without blocking hardware I/O.
"""

import time
import state

# Sequence of valve flow states to cycle through automatically
FLOW_STATES = [1, 2, 3, 4, 0]

# Dwell time (seconds) to hold each flow state before advancing to the next
STEP_INTERVAL_SEC = 5.0


def run_auto_loop():
    """
    Main execution loop for the automated sequence engine.
    Runs continuously on a dedicated background thread.
    """
    state.log_event("Automated Sequence thread initialized.", "INFO")
    current_idx = 0

    while True:
        # 1. Check if the system is currently in Automatic Acquisition Mode
        if state.telemetry_data.get("mode") == "AUTOMATIC ACQUISITION":
            target_state = FLOW_STATES[current_idx]
            
            # Dispatch command through thread-safe queue to avoid hardware race conditions
            state.enqueue_command({"cmd": "SET_FLOW_STATE", "state": target_state})
            
            # Advance to the next flow state in the sequence (wraps around at index end)
            current_idx = (current_idx + 1) % len(FLOW_STATES)

            # 2. Responsive step delay interval
            # Polls every 0.1s instead of a single 5.0s sleep to allow an immediate abort 
            # if the user toggles to Manual Mode or triggers an Emergency Stop (ESTOP).
            start_time = time.time()
            while time.time() - start_time < STEP_INTERVAL_SEC:
                time.sleep(0.1)
                
                # Abort wait loop immediately if mode changes mid-step
                if state.telemetry_data.get("mode") != "AUTOMATIC ACQUISITION":
                    current_idx = 0
                    break
        else:
            # System is in Manual Override or ESTOP state: keep index reset and poll periodically
            current_idx = 0
            time.sleep(0.5)