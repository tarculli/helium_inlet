================================================================================
            HELIUM MASS SPECTROMETER (MS) INLET SYSTEM v3
                      LAB CONTROL & TELEMETRY SOFTWARE
================================================================================

1. OVERVIEW & SYSTEM ARCHITECTURE SCHEMATIC
--------------------------------------------------------------------------------
The Helium Inlet v3 system uses a multi-threaded Python architecture to decouple 
real-time hardware I/O operations from web-based user interactions. 

              +-----------------------------------+
              |      Web Browser / User GUI       |
              |       (web/static/index.html)     |
              +-----------------------------------+
                                ^ |
                 WebSocket Data | | User Commands 
                   & Telemetry  | | (JSON)
                                v v
              +-----------------------------------+
              |       FastAPI Web Server          |
              |         (web/server.py)           |
              +-----------------------------------+
                                ^ |
             Reads Telemetry    | | Enqueues Web Commands
             Data Stream        | | (ESTOP, Mode, Flow State)
                                | v
              +-----------------------------------+
              |    Central State Bus ("Brain")    |
              |            (state.py)             |
              |  - telemetry_data (Dict)          |
              |  - command_queue (Thread-Safe FIFO)|
              |  - system_logs (Rolling Buffer)   |
              +-----------------------------------+
                       ^         |               ^ |
        Pushes Updates |         | Pulls         | | Enqueues Auto Cmds
        & Telemetry    |         | Pending Cmds  | | (When Auto Mode Active)
                       v         v               v | Monitors Mode State
   +---------------------------------+  +---------------------------------+
   |      Hardware I/O Loop          |  |   Automated Sequence Engine     |
   |      (loops/io_loop.py)         |  |      (loops/automatic.py)       |
   +---------------------------------+  +---------------------------------+
                   |
         Driver Calls (SCPI / Serial)
                   |
                   v
   +---------------------------------+
   |    Agilent Hardware Driver      |
   |     (hardware/agilent.py)       |
   +---------------------------------+
                   |
         RS-232 Serial (57600 baud)
                   |
                   v
   +---------------------------------------------------------------+
   |                      PHYSICAL HARDWARE                        |
   |  - Agilent 34970A Mainframe & Multiplexer (Slot 100 & 200)    |
   |  - Clippard Manifold Valve Control Card                       |
   |  - Vacuum Pressure Gauges (Edwards AIM-SL, Penning, Convectron)|
   |  - K-Type Thermocouples (CH 101-104)                        |
   +---------------------------------------------------------------+


2. DIRECTORY & FOLDER STRUCTURE
--------------------------------------------------------------------------------
helium_inlet_v3/
│
├── main.py                  # System launcher & thread initializer
├── state.py                 # Central data store, command queue, & logger
├── config.py                # Hardware settings, pinouts, timings, & state maps
│
├── hardware/
│   └── agilent.py           # Agilent 34970A driver & pressure conversion curves
│
├── loops/
│   ├── io_loop.py           # Background thread for hardware sensor scanning & command execution
│   └── automatic.py        # Background thread for automated step sequences
│
└── web/
    ├── server.py            # FastAPI application & WebSocket telemetry handler
    └── static/
        └── index.html       # Web GUI dashboard & Chart.js live plots


3. SCRIPT DESCRIPTIONS & RESPONSIBILITIES
--------------------------------------------------------------------------------
main.py
  - Primary entry point for launching the software system.
  - Spawns background daemon threads for hardware I/O (`io_loop.py`) and 
    automated state sequencing (`automatic.py`).
  - Starts the Uvicorn web server hosting the FastAPI dashboard.
  - Command: `python main.py`

state.py
  - The single source of truth ("brain") for the application.
  - Contains `telemetry_data`: Global dictionary storing live temperatures, 
    voltages, calculated pressures, relay states, and metadata.
  - Contains `command_queue`: Thread-safe FIFO queue (`queue.Queue`) that 
    accepts command requests from the web interface or auto-sequence engine, 
    preventing serial port write collisions.
  - Contains `log_event()`: In-memory rolling event logger.

config.py
  - Centralized repository for system-wide configuration parameters.
  - Hardware Comms: Serial port paths (`/dev/ttyUSB0`), baud rates, and scan channel assignments.
  - Valve Matrix: Maps physical relay channels (Clippard card) to operational 
    flow states (State 0: Depressurized/Isolated, States 1-4: Active flow paths).
  - System Timings: Polling loops, watchdog refresh rate, and WebSocket push intervals.
  - Safety Limits: Maximum temperature and pressure guardrail thresholds.

hardware/agilent.py
  - Hardware Abstraction Layer (HAL) for the Agilent 34970A Mainframe.
  - Manages low-level PySerial communication and SCPI formatting.
  - Controls relay state switching (`ROUTe:CLOSe`, `ROUTe:OPEn`) for valve control.
  - Performs sensor signal transformations:
      * Thermocouple temperature parsing and fault check (`OPEN / NC`).
      * Edwards AIM-SL Cold Cathode Gauge voltage-to-pressure log-linear interpolation.
      * Trap Penning Gauge exponential pressure calculation.
      * Granville-Phillips 375 Convectron Gauge pressure conversion.

loops/io_loop.py
  - Continuous hardware communication thread (`IOLoop`).
  - Polling Engine: Reads thermocouples and voltage channels from the Agilent 
    mainframe at regular intervals defined in `config.py`.
  - Command Processing: Pulls and executes pending commands from `state.command_queue`.
  - Maintains system connection status and handles auto-reconnect on serial dropouts.

loops/automatic.py
  - Automated Sequence Engine thread (`AutoLoop`).
  - Monitors `state.telemetry_data["mode"]`.
  - When set to "AUTOMATIC ACQUISITION", steps sequentially through defined valve 
    flow states and pushes state commands into `state.command_queue`.
  - Uses responsive sub-interval checking to allow immediate aborts on Emergency 
    Stop (E-STOP) or mode toggles.

web/server.py
  - FastAPI Web Application server interface.
  - Serves static dashboard assets (`index.html`).
  - Operates full-duplex WebSocket endpoint (`/ws/telemetry`):
      * Reads `telemetry_data` stream from `state.py` and broadcasts to browsers.
      * Listens for inbound control actions (State changes, Mode switches, ESTOP) 
        and enqueues them into `state.command_queue`.


4. QUICK START GUIDE
--------------------------------------------------------------------------------
1. Connect the lab computer to the Agilent 34970A via RS-232 serial interface.
2. Open a Linux terminal and navigate to the root directory:
   cd helium_inlet/helium_inlet_v3/
3. Run the application:
   python main.py
4. Open a web browser and navigate to:
   http://localhost:8000  (Local Access)
   http://<LAB_COMPUTER_IP>:8000 (Network Access)