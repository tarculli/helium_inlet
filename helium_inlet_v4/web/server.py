"""
This script launches the web server for our instrument's live data GUI.
It streams live telemetry out to connected clients and listens for incoming 
valve state and safety commands from the UI.
"""

import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import state
from config import WEBSOCKET_PUSH_RATE_SEC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Helium Inlet API")
templates = Jinja2Templates(directory="web/static")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Serves the primary web UI dashboard page (index.html)."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Full-duplex WebSocket endpoint for real-time web interaction.
    Runs two concurrent asynchronous tasks per connected browser tab:
      1. `receive_commands`: Listens for control actions from UI -> queues to state.py
      2. `stream_telemetry`: Pushes global telemetry data from state.py -> UI broadcast
    """
    await websocket.accept()
    logger.info("WebSocket client connected.")

    async def receive_commands():
        """Listens for inbound JSON command payloads sent from client buttons."""
        try:
            while True:
                data = await websocket.receive_json()
                cmd = data.get("command")

                if cmd == "SET_FLOW_STATE":
                    state.enqueue_command(
                        {"cmd": "SET_FLOW_STATE", "state": data.get("state")}
                    )
                elif cmd == "SET_MODE":
                    state.enqueue_command(
                        {
                            "cmd": "SET_MODE",
                            "auto_mode": data.get("auto_mode", False),
                        }
                    )
                elif cmd == "ESTOP":
                    state.enqueue_command({"cmd": "ESTOP"})
        except WebSocketDisconnect:
            logger.info("Client disconnected (receive loop).")
        except Exception as e:
            logger.error(f"Error processing command payload: {e}")

    async def stream_telemetry():
        """Periodically broadcasts latest system state dictionary to browser client."""
        try:
            while True:
                # Create a thread-safe snapshot to prevent dictionary mutation errors during JSON encoding
                telemetry_snapshot = (
                    state.get_telemetry()
                    if hasattr(state, "get_telemetry")
                    else dict(state.telemetry_data)
                )
                await websocket.send_json(telemetry_snapshot)
                await asyncio.sleep(WEBSOCKET_PUSH_RATE_SEC)
        except WebSocketDisconnect:
            logger.info("Client disconnected (stream loop).")
        except Exception as e:
            logger.error(f"Error streaming telemetry payload: {e}")

    recv_task = asyncio.create_task(receive_commands())
    send_task = asyncio.create_task(stream_telemetry())

    done, pending = await asyncio.wait(
        [recv_task, send_task], return_when=asyncio.FIRST_COMPLETED
    )

    # Cancel pending tasks and await them to cleanly handle CancelledError exceptions
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass