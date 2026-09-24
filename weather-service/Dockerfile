FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8002

# No URLs or secrets are baked in; the Open-Meteo URLs are public constants in app/main.py.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
