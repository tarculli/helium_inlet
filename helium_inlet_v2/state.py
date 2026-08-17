'''
This script serves as the central controller and state manager for the Helium MS program. 
It collects telemetry from hardware loops (e.g., Watchdog, Agilent), maintains the system command queue, 
and interfaces with the web API to ensure safe, coordinated system operation.
'''

import time
from queue import Queue

# Setting the maximum log entries based on the parameter noted by the config.py file in /helium_inlet_v2/
from config import MAX_LOG_ENTRIES

# Thread-safe queue for hardware commands (e.g., {"device": "agilent", "cmd": "OPEN_VALVE_A"})
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