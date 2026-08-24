'''
This script runs the Helium MS system from the lab computer terminal.
To start the system, navigate to helium_inlet/helium_inlet_v2/ and run:
python main.py
It calls background loops from /loops, spawns them in concurrent threads, 
and launches the web API for real-time instrument monitoring.
'''

import threading
import uvicorn

# Importing loop scripts
from loops.io_loop import run_io_loop
from automatic import run_auto_loop

# Local state manager
import state 

if __name__ == "__main__":
    state.log_event("Helium Inlet System Initializing...", "INFO")

    # Start Background Loops
    threading.Thread(target=run_io_loop, daemon=True, name="IOLoop").start()
    threading.Thread(target=run_auto_loop, daemon=True, name="AutoLoop").start()

    # Launch Web Server
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=False)