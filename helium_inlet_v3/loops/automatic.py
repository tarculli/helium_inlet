"""
loops/automatic.py - Automated Sequence Engine

Executes temperature- and time-dependent valve flow state sequences.
Runs as a background thread monitoring state.telemetry_data["mode"].
"""

import time
import state

# Fallback defaults if not present in config.py
try:
    import config
    COLD_POINT_TEMP = getattr(config, "COLD_POINT_TEMP", 30.0)  # Kelvin or °C threshold
    MAX_SAMPLING_TIME = getattr(config, "MAX_SAMPLING_TIME", 10.0)  # Seconds
except ImportError:
    print("config.py import error! ...do not run!")
    COLD_POINT_TEMP = 30.0
    MAX_SAMPLING_TIME = 10.0

POLL_INTERVAL_SEC = 0.1  # Responsive check rate for aborts/mode changes


def get_trap_temp(trap_id: str) -> float:
    """Fetches numerical trap temperature from telemetry using exact IO loop value keys."""
    telemetry = getattr(state, "telemetry_data", {})
    
    # Primary and secondary numeric value keys populated by io_loop.py
    keys = ["ch104_val", "ch103_val"] if trap_id == "A" else ["ch101_val", "ch102_val"]

    for key in keys:
        val = telemetry.get(key)
        if val is not None and isinstance(val, (int, float)):
            return float(val)

    return 999.0


def set_system_flow_state(flow_state: int, current_active_state: int) -> int:
    """Enqueues state command if changing to a new state."""
    if flow_state != current_active_state:
        state.enqueue_command({"cmd": "SET_FLOW_STATE", "state": flow_state})
        state.log_event(f"Auto Loop Transition -> Flow State {flow_state}", "INFO")
    return flow_state


def run_auto_loop():
    """
    Main state-machine loop executing:
      1. FS5: Cool Trap A to waste until T_A < COLD_POINT_TEMP.
      2. FS1: Sample to Trap A while Trap B cools to waste (MAX_SAMPLING_TIME).
      3. Switch evaluation: If Trap B cold -> FS2, else -> FS6 (B to waste, A isolated).
      4. FS2: Sample to Trap B while Trap A thaws/cools to waste (MAX_SAMPLING_TIME).
      5. Switch evaluation: If Trap A cold -> FS1, else -> FS5 (A to waste, B isolated).
    """
    state.log_event("Automated Sequence thread initialized.", "INFO")

    # Internal sequence phase states: "STARTUP", "SAMPLING_A", "WAIT_COOL_B", "SAMPLING_B", "WAIT_COOL_A"
    seq_phase = "STARTUP"
    current_flow_state = None
    sampling_start_time = None

    while True:
        # Check system mode
        if state.telemetry_data.get("mode") != "AUTOMATIC ACQUISITION":
            # Reset sequence engine state when paused, in manual, or in ESTOP
            seq_phase = "STARTUP"
            current_flow_state = None
            sampling_start_time = None
            time.sleep(0.5)
            continue

        temp_a = get_trap_temp("A")
        temp_b = get_trap_temp("B")

        # ------------------------------------------------------------------
        # PHASE 1: Startup / Pre-cooling Trap A
        # ------------------------------------------------------------------
        if seq_phase == "STARTUP":
            current_flow_state = set_system_flow_state(5, current_flow_state)
            
            if temp_a < COLD_POINT_TEMP:
                state.log_event(f"Trap A cooled below threshold ({temp_a}K). Starting sample cycle.", "INFO")
                seq_phase = "SAMPLING_A"
                sampling_start_time = time.time()

        # ------------------------------------------------------------------
        # PHASE 2: Trap A Active Sampling (FS1)
        # ------------------------------------------------------------------
        elif seq_phase == "SAMPLING_A":
            current_flow_state = set_system_flow_state(1, current_flow_state)
            
            elapsed = time.time() - sampling_start_time
            if elapsed >= MAX_SAMPLING_TIME:
                if temp_b < COLD_POINT_TEMP:
                    state.log_event("Max sampling time reached for Trap A. Trap B is cold -> Switching to Trap B (FS2).", "INFO")
                    seq_phase = "SAMPLING_B"
                    sampling_start_time = time.time()
                else:
                    state.log_event("Max sampling time reached for Trap A. Trap B NOT cold -> Holding in FS6.", "WARN")
                    seq_phase = "WAIT_COOL_B"

        # ------------------------------------------------------------------
        # PHASE 3: Wait for Trap B to Cool (FS6)
        # ------------------------------------------------------------------
        elif seq_phase == "WAIT_COOL_B":
            current_flow_state = set_system_flow_state(6, current_flow_state)
            
            if temp_b < COLD_POINT_TEMP:
                state.log_event(f"Trap B cooled below threshold ({temp_b}K) -> Transitioning to Trap B (FS2).", "INFO")
                seq_phase = "SAMPLING_B"
                sampling_start_time = time.time()

        # ------------------------------------------------------------------
        # PHASE 4: Trap B Active Sampling (FS2)
        # ------------------------------------------------------------------
        elif seq_phase == "SAMPLING_B":
            current_flow_state = set_system_flow_state(2, current_flow_state)
            
            elapsed = time.time() - sampling_start_time
            if elapsed >= MAX_SAMPLING_TIME:
                if temp_a < COLD_POINT_TEMP:
                    state.log_event("Max sampling time reached for Trap B. Trap A is cold -> Switching to Trap A (FS1).", "INFO")
                    seq_phase = "SAMPLING_A"
                    sampling_start_time = time.time()
                else:
                    state.log_event("Max sampling time reached for Trap B. Trap A NOT cold -> Holding in FS5.", "WARN")
                    seq_phase = "WAIT_COOL_A"

        # ------------------------------------------------------------------
        # PHASE 5: Wait for Trap A to Cool (FS5)
        # ------------------------------------------------------------------
        elif seq_phase == "WAIT_COOL_A":
            current_flow_state = set_system_flow_state(5, current_flow_state)
            
            if temp_a < COLD_POINT_TEMP:
                state.log_event(f"Trap A cooled below threshold ({temp_a}K) -> Transitioning to Trap A (FS1).", "INFO")
                seq_phase = "SAMPLING_A"
                sampling_start_time = time.time()

        # Responsive thread sleep
        time.sleep(POLL_INTERVAL_SEC)