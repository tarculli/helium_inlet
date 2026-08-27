"""
state.py - Central Data Bus & State Machine

This module acts as the "brain" and single source of truth for the entire 
software system. It manages thread-safe communications between the FastAPI 
web server, automated sequence loops, and the hardware I/O thread.

Key Responsibilities:
1. Holds `telemetry_data` dict broadcasted to web clients via WebSockets.
2. Manages `command_queue` for thread-safe cross-thread execution.
3. Maintains in-memory rolling system log history.
"""

# Necessary imports
import time
from queue import Queue, Empty

# config.py is a convenient place to store settings!
from config import MAX_LOG_ENTRIES

# Thread-safe FIFO queue for incoming hardware & sequence control commands
command_queue = Queue()

# Rolling in-memory storage for UI event logs, 
# ie. emergency stops, flow state changes, warnings, or other important events
system_logs = []


def log_event(message: str, level: str = "INFO"):
    """
    Appends a formatted log entry to the global system log buffer.
    Automatically drops the oldest logs when exceeding MAX_LOG_ENTRIES.
    """
    timestamp = time.strftime("%H:%M:%S")
    system_logs.append({"time": timestamp, "level": level, "msg": message})
    if len(system_logs) > MAX_LOG_ENTRIES:
        system_logs.pop(0)


# GLOBAL TELEMETRY DICTIONARY (live data and system diagnostics)
# Read continuously by web/server.py and updated by loops/io_loop.py
telemetry_data = {
    # System Status & Metadata
    "status": "Initializing...",
    "device": "Disconnected",
    "timestamp": "Waiting for data...",
    "time_str": "00:00:00",
    "logs": system_logs,
    "mode": "MANUAL OVERRIDE",
    "control": {"flow_state": 0},

    # Numeric float values (Used directly by Chart.js in index.html)
    "ch101_val": None, "ch102_val": None, "ch103_val": None, "ch104_val": None,
    "ch115_p_val": None, "ch116_p_val": None, "ch119_p_val": None,

    # Formatted display strings (Used for UI status cards)
    "ch101": "---.-- °C", "ch102": "---.-- °C", "ch103": "---.-- °C", "ch104": "---.-- °C",
    "ch112": "---.-- V", "ch113": "---.-- V",
    "ch115_p": "---.--- Torr", "ch115_v": "---.-- V",
    "ch116_p": "---.--- Torr", "ch116_v": "---.-- V",
    "ch118_p": "N/A", "ch118_v": "N/A",
    "ch119_p": "---.--- Torr", "ch119_v": "---.-- V",
}


def enqueue_command(cmd_dict: dict):
    """
    Thread-safe helper to push a command dictionary into command_queue.
    Normalizes command keys ('command' -> 'cmd') for UI compatibility.
    """
    if "command" in cmd_dict and "cmd" not in cmd_dict:
        cmd_dict["cmd"] = cmd_dict.pop("command")

    command_queue.put(cmd_dict)
    log_event(f"Command queued: {cmd_dict.get('cmd')}")


def process_command_queue(agilent_inst):
    """
    Executes pending commands against the Agilent hardware driver.
    Called periodically within the hardware I/O loop (`loops/io_loop.py`).
    """
    if command_queue.empty():
        return

    try:
        # Non-blocking fetch from FIFO queue
        cmd_data = command_queue.get_nowait()
        cmd_type = cmd_data.get("cmd")

        # 1. Valve Flow State Command
        if cmd_type == "SET_FLOW_STATE":
            state_num = cmd_data.get("state")
            log_event(f"Applying Flow State {state_num}...")
            if agilent_inst.set_flow_state(state_num):
                telemetry_data["control"]["flow_state"] = state_num
                log_event(f"Flow State {state_num} applied successfully.", "SUCCESS")
            else:
                log_event(f"Failed to apply Flow State {state_num}.", "ERROR")

        # 2. Sequence Mode Command (Auto vs Manual)
        elif cmd_type == "SET_MODE":
            is_auto = cmd_data.get("auto_mode", False)
            telemetry_data["mode"] = "AUTOMATIC ACQUISITION" if is_auto else "MANUAL OVERRIDE"
            log_event(f"Mode set to {telemetry_data['mode']}.", "SUCCESS")

        # 3. Emergency Stop (E-STOP) Command
        elif cmd_type == "ESTOP":
            telemetry_data["mode"] = "MANUAL OVERRIDE"
            log_event("ESTOP INITIATED! Terminating sequence.", "WARN")
            if agilent_inst.emergency_stop():
                telemetry_data["control"]["flow_state"] = 0
                log_event("ESTOP Complete: All valves depressurized.", "SUCCESS")
            else:
                log_event("ESTOP failed on hardware!", "ERROR")

        command_queue.task_done()
    except Empty:
        pass