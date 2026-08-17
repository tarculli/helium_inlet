'''
This script serves as the central controller and state manager for the Helium MS program. 
It collects telemetry from hardware loops (e.g., Watchdog, Agilent), maintains the system command queue, 
and interfaces with the web API to ensure safe, coordinated system operation.
'''

import time
from queue import Queue, Empty

# Setting parameters and configurations from config.py
from config import MAX_LOG_ENTRIES, STATE_VALVE_MAP

# Thread-safe queue for hardware commands (e.g., {"device": "agilent", "cmd": "SET_FLOW_STATE", "state": 2})
command_queue = Queue()

# List to store important system information, events
system_logs = []

def log_event(message: str, level: str = "INFO"):
    timestamp = time.strftime("%H:%M:%S")
    system_logs.append({"time": timestamp, "level": level, "msg": message})
    if len(system_logs) > MAX_LOG_ENTRIES:
        system_logs.pop(0)

# Stores the current live snapshot of the entire physical system
telemetry_data = {
    "status": "Initializing...",
    "device": "Disconnected",
    "timestamp": "Waiting for data...",
    "logs": system_logs,
    "mode": "READ-ONLY MONITORING",
    
    "control": {
        "flow_state": 1,
        "target_flow_state": 1,
        "is_busy": False,
        "v_waste_a": False,
        "v_waste_b": False,
        "v_ms_inlet": "A",
        "cov_valve": "SAMPLE",
        "heater_a": False,
        "heater_b": False,
        "turbo_waste": True
    },

    "ch104": "---.-- °C", "ch104_val": None,
    "ch103": "---.-- °C", "ch103_val": None,
    "ch101": "---.-- °C", "ch101_val": None,
    "ch102": "---.-- °C", "ch102_val": None,

    "ch115_p": "---.--- Torr", "ch115_p_val": None, "ch115_v": "---.-- V",
    "ch113": "---.-- V",
    "ch116_p": "---.--- Torr", "ch116_p_val": None, "ch116_v": "---.-- V",
    "ch112": "---.-- V",
    "ch118_p": "N/A", "ch118_p_val": None, "ch118_v": "N/A",
    "ch119_p": "---.--- Torr", "ch119_p_val": None, "ch119_v": "---.-- V",
}

def enqueue_command(cmd_dict: dict):
    """Pushes an incoming command from API/UI buttons into the queue."""
    command_queue.put(cmd_dict)
    log_event(f"Command queued: {cmd_dict.get('cmd', 'UNKNOWN')}")

def process_command_queue(agilent_inst):
    """
    Pulls staged commands from queue and executes them via the Agilent instance.
    Call this function inside your main hardware communication loop.
    """
    if command_queue.empty():
        return

    try:
        cmd_data = command_queue.get_nowait()
        telemetry_data["control"]["is_busy"] = True

        cmd_type = cmd_data.get("cmd")

        if cmd_type == "SET_FLOW_STATE":
            new_state = cmd_data.get("state")
            if new_state in STATE_VALVE_MAP:
                telemetry_data["control"]["target_flow_state"] = new_state
                log_event(f"Staging transition to Flow State {new_state}...")
                
                success = agilent_inst.set_flow_state(new_state)
                if success:
                    telemetry_data["control"]["flow_state"] = new_state
                    log_event(f"Successfully transition to Flow State {new_state}")
                else:
                    log_event(f"Failed to apply Flow State {new_state} on Agilent hardware", level="ERROR")
            else:
                log_event(f"Invalid flow state requested: {new_state}", level="WARNING")

        elif cmd_type == "ESTOP":
            log_event("ESTOP: Depressurizing all Clippard valves!", level="WARNING")
            success = agilent_inst.emergency_stop()
            if success:
                telemetry_data["control"]["flow_state"] = None
                log_event("ESTOP complete: All valves depressurized.", level="WARNING")
            else:
                log_event("ESTOP command failed on Agilent hardware!", level="ERROR")

        elif cmd_type == "SET_MODE":
            new_mode = cmd_data.get("mode", "READ-ONLY MONITORING")
            telemetry_data["mode"] = new_mode
            log_event(f"System control mode updated to: {new_mode}")

        command_queue.task_done()

    except Empty:
        pass
    except Exception as e:
        log_event(f"Error processing command from queue: {e}", level="ERROR")
    finally:
        telemetry_data["control"]["is_busy"] = False