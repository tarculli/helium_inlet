"""
This script runs the Helium MS system from the lab computer terminal.
To start the system, navigate to helium_inlet/helium_inlet_v3/ and run:
"python main.py"
It calls background loops from /loops, starts them in concurrent threads, 
and launches the web API for real-time instrument monitoring and control.
"""

import threading
import uvicorn

# Importing state.py, which is the "brain" of our software system, serving as a central point of control
import state

# Importing state machine loops:
# - io_loop: Controls input/output stream and telemetry polling for the Agilent 34970A
# - automatic: Automation sequence loop responsible for continuous system operation
from loops.io_loop import run_io_loop
from loops.automatic import run_auto_loop

if __name__ == "__main__":
    state.log_event("Helium Inlet System v3 Initializing...", "INFO")

    # Start Hardware I/O Thread (daemon=True ensures thread exits on script stop)
    threading.Thread(target=run_io_loop, daemon=True, name="IOLoop").start()

    # Start Automated Sequence Thread
    threading.Thread(target=run_auto_loop, daemon=True, name="AutoLoop").start()

    # Launch Web Server (accessible locally via port 8000)
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=False)