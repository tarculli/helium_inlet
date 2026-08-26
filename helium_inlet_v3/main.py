'''
This script runs the Helium MS system from the lab computer terminal.
To start the system, navigate to helium_inlet/helium_inlet_v2/ and run:
python main.py
It calls background loops from /loops, spawns them in concurrent threads, 
and launches the web API for real-time instrument monitoring.
'''

import threading
import uvicorn
import state
from loops.io_loop import run_io_loop
from loops.automatic import run_auto_loop

if __name__ == "__main__":
    state.log_event("Helium Inlet System v3 Initializing...", "INFO")

    # Start Hardware I/O Thread
    threading.Thread(target=run_io_loop, daemon=True, name="IOLoop").start()

    # Start Automated Sequence Thread
    threading.Thread(target=run_auto_loop, daemon=True, name="AutoLoop").start()

    # Launch Web Server
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=False)