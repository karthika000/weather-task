FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Includes templates/ and static/ for the browser UI.
COPY app/ ./app/

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# TASK_SERVICE_URL and WEATHER_SERVICE_URL are supplied at runtime
# (docker run -e / Kubernetes), not baked into the image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
