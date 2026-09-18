"""
This script launches the Helium Inlet Telemetry & Control system (v4).
It initializes concurrent hardware I/O and automation state machine threads,
then exposes the ASGI web dashboard via Uvicorn.

To run:
    python main.py
"""

import logging
import signal
import sys
import threading
import uvicorn

import state
from loops.automatic import run_auto_loop
from loops.io_loop import run_io_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def shutdown_handler(sig=None, frame=None):
    """Graceful shutdown hook to safely isolate hardware and terminate background loops."""
    logger.info("Shutdown signal received. Initiating hardware safing sequence...")
    
    # Signal background worker loops to exit cleanly
    state.is_running = False
    
    # Enqueue emergency shutdown command to isolate valves
    try:
        state.enqueue_command({"cmd": "ESTOP"})
        logger.info("Failsafe ESTOP command queued.")
    except Exception as e:
        logger.error(f"Failed to queue ESTOP on shutdown: {e}")

    state.log_event("System shutting down gracefully.", "WARN")
    sys.exit(0)


if __name__ == "__main__":
    state.log_event("Helium Inlet System v4 Initializing...", "INFO")
    state.is_running = True

    # Register OS signal handlers for graceful exit (Ctrl+C / SIGTERM)
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start Hardware I/O Thread
    io_thread = threading.Thread(target=run_io_loop, daemon=True, name="IOLoop")
    io_thread.start()

    # Start Automated Sequence Thread
    auto_thread = threading.Thread(
        target=run_auto_loop, daemon=True, name="AutoLoop"
    )
    auto_thread.start()

    logger.info("Dashboard active at: http://localhost:8000")

    try:
        uvicorn.run(
            "web.server:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info",
        )
    finally:
        shutdown_handler()