'''
This script runs the Helium MS system from the lab computer terminal.
To start the system, navigate to helium_inlet/helium_inlet_v2/ and run:
python main.py
It calls background loops from /loops, spawns them in concurrent threads, 
and launches the web API for real-time instrument monitoring.
'''

import threading
import uvicorn

# Importing our loop scripts from /helium_inlet_v2/loops/
from loops.io_loop import run_io_loop
# from loops.watchdog import run_watchdog 
# from loops.state_machine import run_state_machine

# Local script in /helium_inlet_v2 which serves as the centralized state manager 
# and event logger (ie. the "brain" of our program), connecting our background 
# hardware loops, command queue, and the web API
import state 

if __name__ == "__main__":
    state.log_event("Helium Inlet System Initializing...", "INFO")

    # Start Background Loops
    threading.Thread(target=run_io_loop, daemon=True, name="IOLoop").start()
    
    # threading.Thread(target=run_watchdog, daemon=True, name="Watchdog").start()
    # threading.Thread(target=run_state_machine, daemon=True, name="StateMachine").start()

    # Launch Web Server
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=False)