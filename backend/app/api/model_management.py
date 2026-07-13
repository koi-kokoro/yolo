"""Bearer-protected, read-only model management routes."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.entity.model_management_schemas import (
    ModelManagementList,
    ModelManagementModel,
    ModelManagementOverview,
)
from app.services.model_management import model_management_service

router = APIRouter(
    prefix="/api/model-management",
    tags=["只读模型管理"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/overview", response_model=ModelManagementOverview)
def overview():
    """Return a compact overview plus both configured models."""
    return model_management_service.overview()


@router.get("/models", response_model=ModelManagementList)
def list_models():
    """Return exactly the configured deployment and training models."""
    items = model_management_service.models()
    return {"total": len(items), "items": items}


@router.get("/models/{model_id}", response_model=ModelManagementModel)
def get_model(model_id: str):
    """Return one configured model by its stable public identifier."""
    model = model_management_service.get(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    return model
