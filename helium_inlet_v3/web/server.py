'''
This script launches the web server for our instrument's live data GUI.
It streams live telemetry out to connected clients and listens for incoming 
valve state and safety commands from the UI.
'''

import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import state
from config import WEBSOCKET_PUSH_RATE_SEC

app = FastAPI(title="Helium Inlet API")
templates = Jinja2Templates(directory="web/static")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async def receive_commands():
        try:
            while True:
                data = await websocket.receive_json()
                cmd = data.get("command")
                if cmd == "SET_FLOW_STATE":
                    state.enqueue_command({"cmd": "SET_FLOW_STATE", "state": data.get("state")})
                elif cmd == "SET_MODE":
                    state.enqueue_command({"cmd": "SET_MODE", "auto_mode": data.get("auto_mode", False)})
                elif cmd == "ESTOP":
                    state.enqueue_command({"cmd": "ESTOP"})
        except (WebSocketDisconnect, Exception):
            pass

    async def stream_telemetry():
        try:
            while True:
                await websocket.send_json(state.telemetry_data)
                await asyncio.sleep(WEBSOCKET_PUSH_RATE_SEC)
        except (WebSocketDisconnect, Exception):
            pass

    recv_task = asyncio.create_task(receive_commands())
    send_task = asyncio.create_task(stream_telemetry())

    done, pending = await asyncio.wait([recv_task, send_task], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()