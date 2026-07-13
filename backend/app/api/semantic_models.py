"""Semantic model lifecycle API routes (evaluate / export / download / predict)."""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database.session import get_db
from app.entity.db_models import User
from app.entity.schemas import (
    SemanticEvaluateRequest,
    SemanticEvaluateResponse,
    SemanticExportRequest,
    SemanticExportResponse,
    SemanticPredictResponse,
)
from app.services.semantic_model_ops import semantic_model_ops
from app.utils.image_validation import validate_upload

router = APIRouter(prefix="/api/semantic-models", tags=["语义分割模型管理"])


def _current_user_id(current_user: User = Depends(get_current_user)) -> int:
    return current_user.id


@router.post("/evaluate", response_model=SemanticEvaluateResponse)
async def evaluate_model(
    request: SemanticEvaluateRequest | None = None,
    _current_user=Depends(get_current_user),
):
    """Evaluate the semantic segmentation model on the LoveDA validation set.

    Returns cached metrics.json when available; set ``force=true`` to re-run full
    validation against the local PT checkpoint and dataset.
    """
    if request is None:
        request = SemanticEvaluateRequest()
    result = semantic_model_ops.evaluate(device=request.device, force=request.force)
    return result


@router.post("/export", response_model=SemanticExportResponse)
async def export_model(
    request: SemanticExportRequest | None = None,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Export the current semantic artifact as a versioned ModelVersion."""
    if request is None:
        request = SemanticExportRequest()
    return semantic_model_ops.export(
        db=db,
        version=request.version,
        description=request.description,
        set_default=request.set_default,
        upload_minio=request.upload_minio,
    )


@router.get("/download/{version_id}")
async def download_model(
    version_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """Download the PT weight file for a semantic model version."""
    info = semantic_model_ops.get_download_path(version_id, db)
    return FileResponse(
        path=info["file_path"],
        media_type="application/octet-stream",
        filename=info["filename"],
    )


@router.get("/versions")
async def list_versions(
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """List registered semantic segmentation model versions."""
    items = semantic_model_ops.list_versions(db)
    return {"total": len(items), "items": items}


@router.post("/predict", response_model=SemanticPredictResponse)
async def predict_image(
    file: UploadFile = File(..., description="测试图片"),
    use_pt_fallback: bool = Form(True, description="ONNX 缺失时是否回退到 PT 推理"),
    _current_user=Depends(get_current_user),
):
    """Upload a test image and run semantic segmentation inference.

    Returns a base64-encoded overlay image plus per-class pixel statistics.
    """
    validated = await validate_upload(file)
    try:
        result = semantic_model_ops.predict(validated.image, use_pt_fallback=use_pt_fallback)
        return result
    finally:
        validated.cleanup()
