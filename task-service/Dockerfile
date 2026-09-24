FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8001

# DATABASE_URL is supplied at runtime (docker run -e / Kubernetes), not baked in.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
