================================================================================
            HELIUM MASS SPECTROMETER (MS) INLET SYSTEM version 3
                          LAB CONTROL SOFTWARE
================================================================================

1. OVERVIEW & SYSTEM ARCHITECTURE SCHEMATIC
--------------------------------------------------------------------------------
The Helium Inlet v3 system uses a multi-threaded Python architecture (parallel tasks) to decouple 
real-time hardware input/output operations from web-based user interactions. 

              +-----------------------------------------------+
              |            Web Browser / User GUI             |
              |                  CONTROL HUB                  |
              |             (web/static/index.html)           |
              +-----------------------------------------------+
                                      ^ |
         WebSocket Data & Telemetry   | | User Commands 
         Communication Line           | | (in JSON)
                                      v v
              +-----------------------------------------------+
              |              FastAPI Web Server               |
              |                (web/server.py)                |
              +-----------------------------------------------+
                                      ^ |
         Reads Telemetry              | | Passes Web GUI Commands
         Data Stream                  | | (Close All Valves, Mode, etc.)
                                      | v
              +-----------------------------------------------+
              |            Central State ("Brain")            |
              |                  (state.py)                   |
              |  - telemetry_data (dict)                      |
              |  - command_queue (thread-safe FIFO)           |
              |  - system_logs (rolling buffer to cap usage)  |
              +-----------------------------------------------+
                       ^         |               ^
        Pushes Updates |         | Pulls         | Queues Auto Cmds
        & Telemetry    |         | Pending Cmds  | (When Auto Mode Active)
                       |         |               | Monitors Mode State
                       v         v               v
   +---------------------------------+  +---------------------------------+
   |        Hardware I/O Loop        |  |    Automated Sequence Engine    |
   |       (loops/io_loop.py)        |  |      (loops/automatic.py)       |
   +---------------------------------+  +---------------------------------+
                   |
         Driver Calls (SCPI / Serial)
                   |
                   v
   +---------------------------------+
   |     Agilent Hardware Driver     |
   |      (hardware/agilent.py)      |
   +---------------------------------+
                   |
         RS-232 Serial (57600 baud)
                   |
                   v
   +---------------------------------------------------------------+
   |                       PHYSICAL HARDWARE                       |
   |  - Agilent 34970A Mainframe & Multiplexer (Slot 100 & 200)    |
   |  - Clippard Manifold Valve Control Card                       |
   |  - Vacuum Pressure Gauges (Edwards AIM-SL, Penning, Convectron)|
   |  - K-Type Thermocouples (CH 101-104)                           |
   +---------------------------------------------------------------+


2. DIRECTORY & FOLDER STRUCTURE
--------------------------------------------------------------------------------
helium_inlet_v3/
│
├── main.py                  # System launcher & parallel thread initializer
├── state.py                 # Central data store, command queue, & event logger
├── config.py                # Hardware settings, channel maps, timings, safety thresholds, & state configurations
│
├── hardware/
│   └── agilent.py           # Agilent 34970A driver & pressure conversion functions
│
├── loops/
│   ├── io_loop.py           # Background thread for hardware sensor telemetry scanning & command execution
│   └── automatic.py        # Background thread for automated sequence to cycle between traps
│
└── web/
    ├── server.py            # FastAPI application & WebSocket telemetry handler
    └── static/
        └── index.html       # Web GUI dashboard & Chart.js live plots


3. SCRIPT DESCRIPTIONS & RESPONSIBILITIES
--------------------------------------------------------------------------------
main.py
  - Primary entry point for launching the software system. (run 'python main.py')
  - Initiates background threads for hardware I/O (`io_loop.py`) and 
    automated state sequencing (`automatic.py`).
  - Starts the Uvicorn web server hosting the FastAPI dashboard.

state.py
  - The single shared source of truth ("brain") for our pipeline.
  - Contains `telemetry_data`: Global dictionary storing live temperatures, 
    voltages, calculated pressures, relay states, and other metadata.
  - Contains `command_queue`: Thread-safe FIFO (first in, first out) queue (`queue.Queue`) that 
    accepts command requests from the web interface or auto-sequence engine, 
    preventing serial port write collisions.
  - Contains `log_event()`: In-memory rolling event logger.

config.py
  - Centralized repository for system-wide configuration parameters.
  - Hardware Comms: Serial port paths (`/dev/ttyUSB0`), baud rates, and Agilent channel assignments.
  - Valve Matrix: Maps physical relay channels (Clippard card) to operational flow states (eg. States 1-6: Active flow paths).
  - System Timings: Polling loops, watchdog refresh rate, and WebSocket push intervals.
  - Safety Limits: Maximum temperature and pressure guardrail thresholds.

hardware/agilent.py
  - Communication and control for the Agilent 34970A.
  - Manages low-level PySerial communication and SCPI formatting.
  - Controls relay state switching (`ROUTe:CLOSe`, `ROUTe:OPEn`) for valve control.
  - Performs sensor signal conversions/transformations:
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
  - Automated thread (`AutoLoop`) to run continuous switching between Trap A and B!
  - Monitors `state.telemetry_data["mode"]`.
  - When set to "AUTOMATIC ACQUISITION", steps sequentially through defined valve 
    flow states and pushes state commands into `state.command_queue`.
  - Uses responsive sub-interval checking to allow immediate aborts on Emergency 
    Stop (E-STOP) or mode toggles.

  Automatic loop sequence (pseudo 10 second changeover for now...):

    - Startup sequence logic: if Trap A is colder than "COLD_POINT_TEMP", begin cycle between FS1 and FS2, else, start with...
    
    1) Trap A is cooling and pumping to waste – Flow State 5 (until T < COLD_POINT_TEMP)

    Then... 

    2) Trap A is cold and receiving sample gas, Trap B is cooling and pumping to waste – Flow State 1 (need to add roughing subsequence later)

    3) If Trap A has been receiving sample gas for more than MAX_SAMPLING_TIME, then switch to Trap B if it is cold, otherwise set to FS6 so B continues to waste but A is isolated?

    4) Trap B is cold and receiving sample gas, Trap A is thawing and pumpinh to waste – Flow State 2 (need to add roughing subsequence later)

    5) Similar switching logic as above...

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
   'cd helium_inlet/helium_inlet_v3/'
3. Run the application:
   'python main.py'
4. Open a web browser and navigate to:
   http://localhost:8000  (Local Access)
   http://<LAB_COMPUTER_IP>:8000 (Network Access)