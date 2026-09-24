import logging
import os
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# INFO logging also shows httpx's "HTTP Request: ..." lines, i.e. every REST call
# this service makes to the Task Service and the Weather Service.
logging.basicConfig(level=logging.INFO)

# Addresses of the other microservices. The defaults are for local development;
# in Kubernetes these are set to the internal Service names.
TASK_SERVICE_URL = os.environ.get("TASK_SERVICE_URL", "http://localhost:8001")
WEATHER_SERVICE_URL = os.environ.get("WEATHER_SERVICE_URL", "http://localhost:8002")
TIMEOUT_SECONDS = 5.0

APP_DIR = Path(__file__).parent

app = FastAPI(title="WeatherTask Web Service")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


def call_service(service_name: str, method: str, url: str, json: dict | None = None) -> Response:
    """Forward a REST request to another microservice and relay its answer.

    - The downstream status code and JSON body are passed through unchanged,
      so e.g. 201, 404 and 422 from the Task Service reach the browser as-is.
    - If the service cannot be reached (timeout / connection error) -> 503.
    - If it answers with something that is not JSON -> 502.
    """
    try:
        response = httpx.request(method, url, json=json, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        raise HTTPException(status_code=503, detail=f"{service_name} timed out")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail=f"{service_name} unavailable")

    if response.status_code == 204:
        return Response(status_code=204)

    try:
        body = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail=f"{service_name} returned an invalid response")

    return JSONResponse(content=body, status_code=response.status_code)


# ---------- Browser user interface ----------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(APP_DIR / "templates" / "index.html")


@app.get("/health")
def health():
    return {"status": "healthy"}


# ---------- REST API used by the browser ----------
# Task data is never stored here and the database is never accessed here:
# every task operation is forwarded to the Task Service REST API.

@app.get("/api/tasks")
def list_tasks():
    return call_service("Task Service", "GET", f"{TASK_SERVICE_URL}/tasks")


@app.post("/api/tasks")
def create_task(
    task: dict = Body(examples=[{"title": "Go running", "city": "Stockholm", "due_date": "2026-09-26"}]),
):
    # Validation is done by the Task Service (its 422 errors are passed back).
    return call_service("Task Service", "POST", f"{TASK_SERVICE_URL}/tasks", json=task)


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, changes: dict = Body(examples=[{"completed": True}])):
    return call_service("Task Service", "PATCH", f"{TASK_SERVICE_URL}/tasks/{task_id}", json=changes)


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    return call_service("Task Service", "DELETE", f"{TASK_SERVICE_URL}/tasks/{task_id}")


@app.get("/api/weather/{city}")
def get_weather(city: str):
    # quote() makes the city safe to put in a URL path (spaces, "/", å, ö ...).
    return call_service("Weather Service", "GET", f"{WEATHER_SERVICE_URL}/weather/{quote(city, safe='')}")
