'''
This script sets the various parameters needed in the rest of our program.
It's just a neat way to store all this information and make quick tweaks.
'''

# Hardware Communications
AGILENT_PORT = "/dev/ttyUSB0"
AGILENT_BAUD = 57600
TC_CHANNELS = "101,102,103,104"
VOLT_CHANNELS = "112,113,115,116,118,119"

# Clippard Valve Card & Flow State Configurations (Slot 2: Channels 201–220)
VALVE_SLOT_PREFIX = 200
VALVE_CHANNELS = {
    "V1": 8,  # EV5 (Peach/Orange) -> 208
    "V2": 9,  # EV6 (Yellow)       -> 209
    "V3": 6,  # EV3 (Red)          -> 206
    "V4": 7,  # EV4 (Green)        -> 207
}

STATE_VALVE_MAP = {
    0: [],                  # State 0: All Valves Depressurized / Isolated (Startup Default)
    1: ["V1", "V4"],        # Sample -> Trap A | Trap B -> Waste
    2: ["V2", "V3"],        # Sample -> Trap B | Trap A -> Waste
    3: ["V1", "V3", "V4"],  # Sample -> Trap A | No Waste
    4: ["V1", "V2", "V3"],  # Sample -> Trap B | No Waste
}

# Timings
IO_POLL_RATE_SEC = 1.0
WATCHDOG_RATE_SEC = 0.5
STATE_MACHINE_RATE_SEC = 1.0
WEBSOCKET_PUSH_RATE_SEC = 1.0

# Safety Thresholds (Placeholders for Watchdog)
MAX_TRAP_TEMP_C = 50.0
MAX_CHAMBER_PRESSURE_TORR = 1e-3

# UI Limits
MAX_LOG_ENTRIES = 50