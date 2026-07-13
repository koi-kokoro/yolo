"""Protected Semantic MVP API routes."""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database.session import get_db
from app.entity.schemas import SemanticModelInfo, SemanticTaskCreateResponse, SemanticTaskDetail, SemanticTaskPage
from app.services.semantic_runtime import semantic_runtime
from app.services.semantic_task_service import semantic_task_service
from app.storage.minio_client import MinIOClient
from app.utils.image_validation import validate_upload

router = APIRouter(prefix="/api/semantic-tasks", tags=["语义分割"])


def _model(model) -> dict:
    return {"id": model.id, "version": model.version, "model_name": model.model_name}


def _summary(task) -> dict:
    result = task.result
    return {"task_uuid": task.task_uuid, "status": task.status, "original_filename": task.original_filename, "model_version": _model(task.model_version), "image_width": task.image_width, "image_height": task.image_height, "inference_time_ms": result.inference_time_ms if result else None, "total_time_ms": result.total_time_ms if result else None, "created_at": task.created_at, "started_at": task.started_at, "completed_at": task.completed_at}


@router.get("/model-info", response_model=SemanticModelInfo)
def model_info(_current_user=Depends(get_current_user)):
    return semantic_runtime.model_info()


@router.post("", response_model=SemanticTaskCreateResponse, status_code=202)
async def create_task(file: UploadFile = File(...), current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    semantic_task_service.check_create_allowed(db, current_user.id)
    validated = await validate_upload(file)
    try:
        task = semantic_task_service.create(db, current_user.id, validated)
        return {"id": task.id, "task_uuid": task.task_uuid, "status": task.status, "model_version": _model(task.model_version), "original_filename": task.original_filename, "created_at": task.created_at}
    finally:
        validated.cleanup()


@router.get("", response_model=SemanticTaskPage)
def list_tasks(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status: str | None = None, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    total, total_pages, items = semantic_task_service.list_owned(db, current_user.id, page, page_size, status)
    return {"total": total, "page": page, "page_size": page_size, "total_pages": total_pages, "items": [_summary(item) for item in items]}


@router.get("/{task_uuid}", response_model=SemanticTaskDetail)
def get_task(task_uuid: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    task = semantic_task_service.get_owned(db, task_uuid, current_user.id)
    storage = MinIOClient()
    result = None
    source_url = None
    if task.status == "succeeded" and task.result:
        source_url = storage.get_presigned_url(task.source_object_key)
        result = {"index_mask_url": storage.get_presigned_url(task.result.index_mask_object_key), "color_mask_url": storage.get_presigned_url(task.result.color_mask_object_key), "overlay_url": storage.get_presigned_url(task.result.overlay_object_key), "class_statistics": task.result.class_statistics, "inference_time_ms": task.result.inference_time_ms, "total_time_ms": task.result.total_time_ms, "inference_metadata": task.result.inference_metadata}
    error = {"code": task.error_code, "message": task.error_message} if task.status == "failed" else None
    return {"task_uuid": task.task_uuid, "status": task.status, "original_filename": task.original_filename, "source_url": source_url, "model_version": _model(task.model_version), "result": result, "error": error, "created_at": task.created_at, "started_at": task.started_at, "completed_at": task.completed_at}
