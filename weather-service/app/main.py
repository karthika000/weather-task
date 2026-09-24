import logging

import httpx
from fastapi import FastAPI, HTTPException

# INFO logging also shows httpx's own "HTTP Request: GET ..." lines, which is
# visible evidence that this service really calls Open-Meteo.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-service")

app = FastAPI(title="WeatherTask Weather Service")

# External REST APIs (Open-Meteo, no API key required).
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 5.0


def call_open_meteo(url: str, params: dict) -> dict:
    """GET an Open-Meteo endpoint and return its JSON body.

    External failures become clean HTTP errors instead of tracebacks:
    - timeout / connection problem / provider 5xx -> 503 Service Unavailable
    - other error status or invalid JSON          -> 502 Bad Gateway
    """
    try:
        response = httpx.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        logger.warning("Open-Meteo request timed out: %s", url)
        raise HTTPException(status_code=503, detail="Weather provider timed out")
    except httpx.RequestError as exc:
        logger.warning("Could not connect to Open-Meteo: %s", exc)
        raise HTTPException(status_code=503, detail="Weather provider unavailable")
    except httpx.HTTPStatusError as exc:
        logger.warning("Open-Meteo returned HTTP %s", exc.response.status_code)
        if exc.response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Weather provider unavailable")
        raise HTTPException(status_code=502, detail="Weather provider returned an error")
    except ValueError:
        logger.warning("Open-Meteo returned invalid JSON")
        raise HTTPException(status_code=502, detail="Invalid response from weather provider")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Invalid response from weather provider")
    return data


@app.get("/")
def root():
    return {
        "service": "weather-service",
        "message": "WeatherTask Weather Service is running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/weather/{city}")
def get_weather(city: str):
    city = city.strip()
    if not city:
        # Rejected before any external request is made.
        raise HTTPException(status_code=422, detail="City must not be empty")

    # Step 1: Weather Service -> Open-Meteo Geocoding API (city name -> coordinates).
    geo_data = call_open_meteo(
        GEOCODING_URL,
        {"name": city, "count": 1, "language": "en", "format": "json"},
    )

    # Open-Meteo leaves out "results" entirely when nothing matches.
    results = geo_data.get("results")
    if not results:
        raise HTTPException(status_code=404, detail="City not found")

    try:
        place = results[0]  # use the best match
        name = place["name"]
        latitude = place["latitude"]
        longitude = place["longitude"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="Invalid response from weather provider")

    # Step 2: Weather Service -> Open-Meteo Forecast API (coordinates -> current weather).
    forecast_data = call_open_meteo(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code,wind_speed_10m",
        },
    )

    try:
        current = forecast_data["current"]
        temperature = current["temperature_2m"]
        weather_code = current["weather_code"]
        wind_speed = current["wind_speed_10m"]
    except (KeyError, TypeError):
        raise HTTPException(status_code=502, detail="Invalid response from weather provider")

    # Step 3: return a small, simplified response (not the raw Open-Meteo data).
    # Units are Open-Meteo's defaults: temperature in °C, wind speed in km/h.
    return {
        "city": name,
        "region": place.get("admin1"),
        "country": place.get("country"),
        "latitude": latitude,
        "longitude": longitude,
        "temperature": temperature,
        "weather_code": weather_code,
        "wind_speed": wind_speed,
    }
