import threading
import uvicorn
from loops.io_loop import run_io_loop
# from loops.watchdog import run_watchdog
# from loops.state_machine import run_state_machine
import state

if __name__ == "__main__":
    state.log_event("System Initializing...", "INFO")

    # Start Background Loops
    threading.Thread(target=run_io_loop, daemon=True, name="IOLoop").start()
    
    # threading.Thread(target=run_watchdog, daemon=True, name="Watchdog").start()
    # threading.Thread(target=run_state_machine, daemon=True, name="StateMachine").start()

    # Launch Web Server
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=False)