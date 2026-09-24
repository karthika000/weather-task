# WeatherTask

WeatherTask is a small task planner that shows the current weather for the city of each task. A user can add a task with a title, a city and an optional due date, mark it as completed, undo that and delete it. For every task the page shows the current temperature, wind speed and weather code for that city, which are retrieved from the public [Open-Meteo](https://open-meteo.com/) REST API.

I built the application for a Cloud Computing assignment. It is split into three Python microservices and a PostgreSQL database, packaged as Docker images on Docker Hub and deployed to Kubernetes.

The design, the reasoning behind it and a discussion of benefits, challenges, security and business implications are in [architecture/architecture.md](architecture/architecture.md).

## Architecture at a glance

```mermaid
flowchart LR
    browser["Browser"]
    subgraph cluster["Kubernetes namespace: weather-task"]
        lb["web-service<br/>LoadBalancer :8000"]
        web["Web Service"]
        task["Task Service<br/>ClusterIP :8001"]
        weather["Weather Service<br/>ClusterIP :8002"]
        db[("PostgreSQL<br/>ClusterIP :5432")]
        pvc[["postgres-pvc<br/>1Gi"]]
    end
    meteo["Open-Meteo REST API"]

    browser -->|HTTP| lb
    lb --> web
    web -->|REST| task
    web -->|REST| weather
    task -->|SQL| db
    db --- pvc
    weather -->|HTTPS REST| meteo
```

| Component | Responsibility | Technology |
|---|---|---|
| Web Service | Serves the browser UI and the `/api/...` REST API. It is the only entry point from outside the cluster and forwards requests to the other two services. | FastAPI, httpx, HTML/CSS/vanilla JavaScript |
| Task Service | Task CRUD REST API. The only component that talks to the database. | FastAPI, SQLAlchemy 2, Psycopg 3 |
| Weather Service | Weather REST API. Calls Open-Meteo (geocoding, then current weather) and returns a simplified response. | FastAPI, httpx |
| PostgreSQL | Stores the tasks on a PersistentVolumeClaim. One replica. | Official `postgres:17` image |

## Repository structure

```
weather-task/
├── web-service/          Web Service (UI + REST API gateway to the other services)
│   ├── app/main.py
│   ├── app/templates/index.html
│   ├── app/static/style.css
│   ├── Dockerfile
│   └── requirements.txt
├── task-service/         Task Service (task CRUD, PostgreSQL access)
│   ├── app/main.py, database.py, models.py, schemas.py
│   ├── Dockerfile
│   └── requirements.txt
├── weather-service/      Weather Service (Open-Meteo client)
│   ├── app/main.py
│   ├── Dockerfile
│   └── requirements.txt
├── kubernetes/           Kubernetes manifests
│   ├── namespace.yaml
│   ├── secret.yaml
│   ├── postgres.yaml
│   ├── task-service.yaml
│   ├── weather-service.yaml
│   └── web-service.yaml
└── architecture/
    └── architecture.md   Architecture documentation and discussion
```

## REST APIs

### Web Service (externally reachable)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Browser user interface |
| GET | `/health` | Health check |
| GET | `/api/tasks` | List tasks (forwarded to the Task Service) |
| POST | `/api/tasks` | Create a task (forwarded to the Task Service) |
| PATCH | `/api/tasks/{task_id}` | Update a task, e.g. `{"completed": true}` |
| DELETE | `/api/tasks/{task_id}` | Delete a task |
| GET | `/api/weather/{city}` | Current weather for a city (forwarded to the Weather Service) |

Status codes from the Task Service and Weather Service (for example 201, 404 and 422) are passed through unchanged. If a downstream service cannot be reached the Web Service returns `503`.

### Task Service (internal)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/tasks` | List all tasks |
| POST | `/tasks` | Create a task, returns `201` with the generated id |
| GET | `/tasks/{task_id}` | Get one task, `404` if it does not exist |
| PATCH | `/tasks/{task_id}` | Partially update a task |
| DELETE | `/tasks/{task_id}` | Delete a task, returns `204` |

A task looks like this:

```json
{"id": 1, "title": "Go running", "city": "Stockholm", "due_date": "2026-09-26", "completed": false}
```

`title` and `city` are required and may not be empty or only whitespace (`422`).

### Weather Service (internal)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/weather/{city}` | Current weather for a city |

Example response:

```json
{"city": "Stockholm", "region": "Stockholm County", "country": "Sweden", "latitude": 59.32938,
 "longitude": 18.06871, "temperature": 16.2, "weather_code": 0, "wind_speed": 12.6}
```

Temperature is in °C and wind speed in km/h (Open-Meteo defaults). An unknown city returns `404`, an empty city `422`, an unreachable provider `503` and an unusable provider response `502`.

Every service also publishes interactive API documentation at `/docs` (FastAPI Swagger UI).

## Docker images

The three custom images are public on Docker Hub. The Kubernetes manifests reference these exact tags and never `:latest`.

| Service | Image |
|---|---|
| Web Service | `karthika212/weather-task-web:1.0` |
| Task Service | `karthika212/weather-task-task:1.0` |
| Weather Service | `karthika212/weather-task-weather:1.1` |
| Database | `postgres:17` (official image, not rebuilt) |

`weather-task-weather:1.1` adds one retry for transient connection failures to Open-Meteo (see [Known limitations](#known-limitations)). Its digest is `sha256:51724b1018ded0ae302ec500b315b328c47375a9d367fefa889cbfca2e46cfd8`.

All three images use `python:3.12-slim`, run as the non-root user `appuser` (uid 1000) and contain no credentials or service addresses. Configuration is passed in at runtime through environment variables.

To rebuild and push an image:

```bash
docker build -t karthika212/weather-task-web:1.0 ./web-service
docker push karthika212/weather-task-web:1.0
```

## Deploying to Kubernetes

### Prerequisites

- A running Kubernetes cluster and `kubectl` configured for it. I tested the project on **Docker Desktop Kubernetes (kind mode, Kubernetes v1.36.1)** on Windows 11.
- A default StorageClass for the PersistentVolumeClaim (Docker Desktop provides `standard`).
- Outbound internet access from the cluster to Docker Hub and Open-Meteo.

### Deploy

Apply the namespace and Secret first, then the database, then the services:

```bash
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/secret.yaml
kubectl apply -f kubernetes/postgres.yaml
kubectl rollout status deployment/postgres -n weather-task --timeout=180s

kubectl apply -f kubernetes/task-service.yaml
kubectl apply -f kubernetes/weather-service.yaml
kubectl apply -f kubernetes/web-service.yaml
kubectl rollout status deployment/task-service -n weather-task --timeout=180s
kubectl rollout status deployment/weather-service -n weather-task --timeout=180s
kubectl rollout status deployment/web-service -n weather-task --timeout=180s
```

`kubectl apply -f kubernetes/` also works, but it applies the files alphabetically, so the Deployments may briefly wait for the Secret.

### Check the deployment

```bash
kubectl get deployments,pods,services,pvc -n weather-task
```

Expected result: four Deployments at `1/1`, `postgres-pvc` `Bound` and these Services:

```
NAME               TYPE           PORT(S)
postgres-service   ClusterIP      5432/TCP
task-service       ClusterIP      8001/TCP
weather-service    ClusterIP      8002/TCP
web-service        LoadBalancer   8000:<node-port>/TCP
```

### Open the application

In the tested Docker Desktop environment the application is available at:

**http://localhost:8000**

Docker Desktop forwards the LoadBalancer port to `localhost`. The `EXTERNAL-IP` shown by `kubectl get service web-service -n weather-task` (for example `172.19.0.5`) is an address on Docker Desktop's internal network and is not used directly from Windows. On another cluster, use the `EXTERNAL-IP` and port `8000` of `web-service`.

Quick checks from a terminal:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/tasks
curl http://localhost:8000/api/weather/Stockholm
```

## Demonstrating scaling and persistence

Each application service has its own Deployment and can be scaled independently:

```bash
kubectl scale deployment task-service    -n weather-task --replicas=3
kubectl scale deployment weather-service -n weather-task --replicas=2
kubectl scale deployment web-service     -n weather-task --replicas=2
kubectl get deployments -n weather-task
kubectl get endpointslices -n weather-task
```

Scale back with `--replicas=1`. PostgreSQL always stays at one replica.

To show that data survives a database pod restart, create a task in the browser and then delete the PostgreSQL pod:

```bash
kubectl get pods -n weather-task -l app=postgres
kubectl delete pod -n weather-task -l app=postgres
kubectl rollout status deployment/postgres -n weather-task --timeout=180s
kubectl get pvc -n weather-task
curl http://localhost:8000/api/tasks
```

Kubernetes creates a new PostgreSQL pod that mounts the same `postgres-pvc`, and the task is still there.

## Configuration

| Variable | Used by | Set in | Value in Kubernetes |
|---|---|---|---|
| `DATABASE_URL` | Task Service | `secret.yaml` | `postgresql+psycopg://weathertask:...@postgres-service:5432/weathertask` |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL | `secret.yaml` | demo values |
| `TASK_SERVICE_URL` | Web Service | `web-service.yaml` | `http://task-service:8001` |
| `WEATHER_SERVICE_URL` | Web Service | `web-service.yaml` | `http://weather-service:8002` |

Services find each other through Kubernetes Service DNS names. No pod IP addresses are configured anywhere.

## Removing the application

```bash
kubectl delete namespace weather-task
```

This removes every resource in the namespace, including `postgres-pvc`. With the Docker Desktop StorageClass (reclaim policy `Delete`) the stored tasks are deleted as well.

## Known limitations

- **Demo credentials.** `kubernetes/secret.yaml` contains deliberately simple, non-production credentials so the project can be deployed with `kubectl apply`. A real deployment should use an external secrets manager instead of committing credentials.
- **No authentication.** Every user sees and edits the same task list.
- **NodePort is not reachable in Docker Desktop kind mode.** I first exposed the Web Service as a NodePort (`30080`). It worked inside the cluster but Docker Desktop's kind mode does not forward NodePorts to Windows, so the final design uses a `LoadBalancer` Service.
- **Intermittent outbound TLS failures in the test environment.** From inside the Docker Desktop kind cluster, roughly 10-15% of HTTPS connections to Open-Meteo failed with TLS errors (`WRONG_VERSION_NUMBER`, `UNEXPECTED_EOF_WHILE_READING`), while the same requests from the Windows host did not fail. Weather Service 1.1 retries a failed connection once after 0.4 seconds. In a 40-request test through the Web Service, successful responses went from 32/40 (1.0) to 39/40 (1.1). This reduces the impact but does not fix the underlying network issue, and a persistent failure still returns a controlled `503` ("Weather unavailable" in the UI).
- **Single database replica.** PostgreSQL is not replicated or backed up. Deleting the namespace deletes the data.
- **Manual scaling only.** I demonstrated scaling with `kubectl scale`. There is no HorizontalPodAutoscaler.
