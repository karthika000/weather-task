from fastapi import FastAPI, HTTPException, Response, status

from app.schemas import TaskCreate, TaskResponse, TaskUpdate

app = FastAPI(title="WeatherTask Task Service")

# Temporary in-memory storage (Stage 2). Replaced by PostgreSQL in a later stage.
# Data is lost when the service restarts.
tasks: dict[int, TaskResponse] = {}
next_id = 1


def get_task_or_404(task_id: int) -> TaskResponse:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/")
def root():
    return {
        "service": "task-service",
        "message": "WeatherTask Task Service is running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks():
    return list(tasks.values())


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    return get_task_or_404(task_id)


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task_in: TaskCreate):
    global next_id
    task = TaskResponse(id=next_id, **task_in.model_dump())
    tasks[task.id] = task
    next_id += 1
    return task


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task_in: TaskUpdate):
    task = get_task_or_404(task_id)

    # Only apply the fields the client actually sent.
    updates = task_in.model_dump(exclude_unset=True)

    # due_date may be set to null to clear it; the other fields may not.
    for field in ("title", "city", "completed"):
        if field in updates and updates[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")

    updated_task = task.model_copy(update=updates)
    tasks[task_id] = updated_task
    return updated_task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    get_task_or_404(task_id)
    del tasks[task_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)
