"""
This script sets the various parameters needed in the rest of our program.
It's just a neat way to store all this information and make quick tweaks.
"""

# ==============================================================================
# HARDWARE COMMUNICATIONS (Agilent 34970A Mainframe)
# ==============================================================================
# RS-232 Serial port path on Linux/macOS (e.g., '/dev/ttyUSB0' or '/dev/tty.usbserial')
AGILENT_PORT = "/dev/ttyUSB0"
AGILENT_BAUD = 57600

# Channel scan configurations for DMM reads
# Channels 101-104: K-type Thermocouples (°C)
TC_CHANNELS = "101,102,103,104"
# Channels 112-119: DC Voltage inputs from pressure transducers (V)
VOLT_CHANNELS = "112,113,115,116,118,119"


# ==============================================================================
# VALVES & FLOW STATE MATRIX
# ==============================================================================
# Base channel prefix for relay multiplexer module installed in Slot 2
VALVE_SLOT_PREFIX = 200

# Physical relay channel mappings for Clippard manifold valve control card
VALVE_CHANNELS = {
    "V1": 8,  # EV5 (Peach/Orange) -> Channel 208
    "V2": 9,  # EV6 (Yellow)       -> Channel 209
    "V3": 6,  # EV3 (Red)          -> Channel 206
    "V4": 7,  # EV4 (Green)        -> Channel 207
}

# Valve truth table defining operational flow paths
# Key: Flow State ID (0-4)
# Value: List of active valve names that must be energized OPEN
STATE_VALVE_MAP = {
    0: [],                  # State 0: All Valves Depressurized / Isolated (Startup Default / E-STOP)
    1: ["V1", "V4"],        # State 1: Sample -> Trap A | Trap B -> Waste
    2: ["V2", "V3"],        # State 2: Sample -> Trap B | Trap A -> Waste
    3: ["V1", "V3", "V4"],  # State 3: Sample -> Trap A | No Waste
    4: ["V1", "V2", "V3"],  # State 4: Sample -> Trap B | No Waste
}


# ==============================================================================
# EXECUTION TIMINGS (Seconds)
# ==============================================================================
IO_POLL_RATE_SEC = 1.0           # Hardware I/O thread scan interval
WATCHDOG_RATE_SEC = 0.5         # Interlock checking interval
STATE_MACHINE_RATE_SEC = 1.0    # Step transition loop timing interval
WEBSOCKET_PUSH_RATE_SEC = 1.0   # UI update broadcast interval over WebSocket


# ==============================================================================
# SAFETY THRESHOLDS & UI LIMITS
# ==============================================================================
# Thermal & vacuum limits used by watchdog background checks
MAX_TRAP_TEMP_C = 50.0
MAX_CHAMBER_PRESSURE_TORR = 1e-3

# Maximum rolling logs retained in state.py memory buffer
MAX_LOG_ENTRIES = 50