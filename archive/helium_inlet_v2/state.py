import time
from queue import Queue, Empty
from config import MAX_LOG_ENTRIES

command_queue = Queue()
system_logs = []

def log_event(message: str, level: str = "INFO"):
    timestamp = time.strftime("%H:%M:%S")
    system_logs.append({"time": timestamp, "level": level, "msg": message})
    if len(system_logs) > MAX_LOG_ENTRIES:
        system_logs.pop(0)

telemetry_data = {
    "status": "Initializing...",
    "device": "Disconnected",
    "timestamp": "Waiting for data...",
    "time_str": "00:00:00",  # Clean timestamp for plot X-axis
    "logs": system_logs,
    "mode": "MANUAL OVERRIDE",
    "control": {"flow_state": 0},

    # Numeric float keys for plotting engines
    "ch101_val": None,
    "ch102_val": None,
    "ch103_val": None,
    "ch104_val": None,

    # Display string keys for UI cards
    "ch101": "---.-- °C", "ch102": "---.-- °C", "ch103": "---.-- °C", "ch104": "---.-- °C",
    "ch112": "---.-- V", "ch113": "---.-- V",
    "ch115_p": "---.--- Torr", "ch115_v": "---.-- V",
    "ch116_p": "---.--- Torr", "ch116_v": "---.-- V",
    "ch118_p": "N/A", "ch118_v": "N/A",
    "ch119_p": "---.--- Torr", "ch119_v": "---.-- V",
}

def enqueue_command(cmd_dict: dict):
    command_queue.put(cmd_dict)
    log_event(f"Command queued: {cmd_dict.get('cmd')}")

def process_command_queue(agilent_inst):
    if command_queue.empty():
        return

    try:
        cmd_data = command_queue.get_nowait()
        cmd_type = cmd_data.get("cmd")

        if cmd_type == "SET_FLOW_STATE":
            state_num = cmd_data.get("state")
            log_event(f"Applying Flow State {state_num}...")
            if agilent_inst.set_flow_state(state_num):
                telemetry_data["control"]["flow_state"] = state_num
                log_event(f"Flow State {state_num} applied successfully.", "SUCCESS")
            else:
                log_event(f"Failed to apply Flow State {state_num}.", "ERROR")

        elif cmd_type == "ESTOP":
            log_event("ESTOP INITIATED!", "WARN")
            if agilent_inst.emergency_stop():
                telemetry_data["control"]["flow_state"] = 0
                log_event("ESTOP Complete: All valves depressurized.", "SUCCESS")
            else:
                log_event("ESTOP failed on hardware!", "ERROR")

        command_queue.task_done()
    except Empty:
        pass