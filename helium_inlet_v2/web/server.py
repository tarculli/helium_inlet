import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import state
from config import WEBSOCKET_PUSH_RATE_SEC

app = FastAPI(title="Helium Inlet API")
# Point directly to where index.html is stored
templates = Jinja2Templates(directory="web/static")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(state.telemetry_data)
            await asyncio.sleep(WEBSOCKET_PUSH_RATE_SEC)
    except (WebSocketDisconnect, Exception):
        pass