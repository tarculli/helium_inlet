"""
This script launches the web server for our instrument's live data GUI.
It streams live telemetry out to connected clients and listens for incoming 
valve state and safety commands from the UI.
"""

import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Importing state.py, which is the "brain" of our software system, serving as a central point of control
import state

# config.py is a convenient place to store settings!
from config import WEBSOCKET_PUSH_RATE_SEC

# Initialize FastAPI application and Jinja2 template directory
app = FastAPI(title="Helium Inlet API")
templates = Jinja2Templates(directory="web/static")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Serves the primary web UI dashboard page (index.html)."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    """
    Full-duplex WebSocket endpoint for real-time web interaction.
    Runs two concurrent asynchronous tasks per connected browser tab:
      1. `receive_commands`: Listens for control actions from UI -> queues to state.py
      2. `stream_telemetry`: Pushes global telemetry data from state.py -> UI broadcast
    """
    await websocket.accept()

    async def receive_commands():
        """Listens for inbound JSON command payloads sent from client buttons."""
        try:
            while True:
                data = await websocket.receive_json()
                cmd = data.get("command")

                # Parse web user intent and dispatch to central thread-safe queue
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
        except (WebSocketDisconnect, Exception):
            pass

    async def stream_telemetry():
        """Periodically broadcasts latest system state dictionary to browser client."""
        try:
            while True:
                await websocket.send_json(state.telemetry_data)
                await asyncio.sleep(WEBSOCKET_PUSH_RATE_SEC)
        except (WebSocketDisconnect, Exception):
            pass

    # Launch receive and transmit tasks concurrently within FastAPI's async event loop
    recv_task = asyncio.create_task(receive_commands())
    send_task = asyncio.create_task(stream_telemetry())

    # Wait until either task finishes (typically triggered when a client closes the web browser tab)
    done, pending = await asyncio.wait(
        [recv_task, send_task], return_when=asyncio.FIRST_COMPLETED
    )

    # Cleanly cancel remaining background task to avoid memory leaks on disconnect
    for task in pending:
        task.cancel()