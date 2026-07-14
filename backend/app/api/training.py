"""Authenticated LoveDA semantic online-training API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database.session import get_db
from app.entity.schemas import TrainingMetricResponse, TrainingTaskCreate, TrainingTaskResponse
from app.training.training_service import TrainingServiceError, training_service

router = APIRouter(prefix="/api/training", tags=["LoveDA 在线训练"])


def _raise(exc: TrainingServiceError):
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/tasks", response_model=TrainingTaskResponse, status_code=201)
def create_training_task(request: TrainingTaskCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        return training_service.create_task(db, current_user.id, request)
    except TrainingServiceError as exc:
        _raise(exc)


@router.get("/tasks")
def list_training_tasks(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        items = training_service.list_tasks(db, current_user.id)
        return {"total": len(items), "items": [TrainingTaskResponse.model_validate(item) for item in items]}
    except TrainingServiceError as exc:
        _raise(exc)


@router.get("/tasks/{task_id}", response_model=TrainingTaskResponse)
def get_training_task(task_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        return training_service.get_task(db, task_id, current_user.id)
    except TrainingServiceError as exc:
        _raise(exc)


@router.get("/tasks/{task_id}/metrics")
def get_training_metrics(task_id: int, after_epoch: int = Query(0, ge=0), db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        metrics = training_service.metrics(db, task_id, current_user.id, after_epoch)
        return {"task_id": task_id, "total": len(metrics), "metrics": [TrainingMetricResponse.model_validate(item) for item in metrics]}
    except TrainingServiceError as exc:
        _raise(exc)


@router.post("/tasks/{task_id}/stop", response_model=TrainingTaskResponse)
def stop_training_task(task_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        return training_service.stop(db, task_id, current_user.id)
    except TrainingServiceError as exc:
        _raise(exc)


@router.get("/tasks/{task_id}/artifacts/{artifact_name}")
def download_training_artifact(task_id: int, artifact_name: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        path = training_service.artifact(db, task_id, current_user.id, artifact_name)
        return FileResponse(path, filename=artifact_name)
    except TrainingServiceError as exc:
        _raise(exc)


# Narrow compatibility aliases for the previous page while migration is in progress.
@router.post("/start", response_model=TrainingTaskResponse, status_code=201, include_in_schema=False)
def legacy_start(request: TrainingTaskCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return create_training_task(request, db, current_user)


@router.get("/status/{task_id}", response_model=TrainingTaskResponse, include_in_schema=False)
def legacy_status(task_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return get_training_task(task_id, db, current_user)


@router.get("/metrics/{task_id}", include_in_schema=False)
def legacy_metrics(task_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return get_training_metrics(task_id, 0, db, current_user)


@router.post("/stop/{task_id}", response_model=TrainingTaskResponse, include_in_schema=False)
def legacy_stop(task_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return stop_training_task(task_id, db, current_user)
