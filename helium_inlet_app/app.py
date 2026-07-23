import asyncio
import random
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Helium Inlet Control System")

# Point to your templates directory
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Serves the main dashboard layout."""
    return templates.TemplateResponse(request=request, name="index.html")

@app.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket):
    """
    Streams channel data to the frontend every 1 second.
    Currently sends dummy data for testing UI bindings.
    """
    await websocket.accept()
    try:
        while True:
            # Mock data representing your DAQ channels
            data = {
                "ch101": round(24.5 + random.uniform(-0.2, 0.2), 1),  # Engine B HR
                "ch102": round(24.8 + random.uniform(-0.2, 0.2), 1),  # Engine B PV
                "ch103": round(22.1 + random.uniform(-0.2, 0.2), 1),  # Engine A PV
                "ch104": round(21.9 + random.uniform(-0.2, 0.2), 1),  # Engine A HR
                "ch112": round(9.8 + random.uniform(-0.05, 0.05), 2), # Trap Turbo Volt
                "ch113": round(9.9 + random.uniform(-0.05, 0.05), 2), # Chamber Turbo Volt
                "ch115": round(2.35 + random.uniform(-0.01, 0.01), 3),# Chamber Penning Volt
                "ch116": "1.2e-6",                                    # Trap Penning Pressure
                "ch118_v": round(4.52 + random.uniform(-0.02, 0.02), 2),# HiVac Volt
                "ch118_p": "7.5e-3",                                  # HiVac Pressure
                "ch119_v": round(5.11 + random.uniform(-0.02, 0.02), 2),# LowVac Volt
                "ch119_p": "7.6e2",                                   # LowVac Pressure
            }
            await websocket.send_json(data)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print("Client disconnected from telemetry feed.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)