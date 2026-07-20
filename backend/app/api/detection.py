"""Authenticated DIOR facility-detection endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.exceptions import DomainError
from app.database.session import get_db
from app.services.facility_detection_service import facility_detection_service
from app.utils.image_validation import ValidatedImage, validate_upload

router = APIRouter(prefix="/api/detection", tags=["DIOR 设施目标检测"])


@router.get("/model-info")
def model_info(_current_user=Depends(get_current_user)):
    return facility_detection_service.model_info()


@router.post("/single")
async def detect_single(
    file: Annotated[UploadFile, File(...)],
    conf: float = Query(default=settings.DIOR_CONF_THRESHOLD, ge=0.01, le=1.0),
    iou: float = Query(default=settings.DIOR_IOU_THRESHOLD, ge=0.01, le=1.0),
    image_size: int = Query(default=settings.DIOR_INPUT_SIZE, ge=320, le=2048),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validated = await validate_upload(file)
    try:
        return facility_detection_service.detect(
            db, current_user.id, [validated], conf, iou, image_size
        )
    finally:
        validated.cleanup()


@router.post("/batch")
async def detect_batch(
    files: Annotated[list[UploadFile], File(...)],
    conf: float = Query(default=settings.DIOR_CONF_THRESHOLD, ge=0.01, le=1.0),
    iou: float = Query(default=settings.DIOR_IOU_THRESHOLD, ge=0.01, le=1.0),
    image_size: int = Query(default=settings.DIOR_INPUT_SIZE, ge=320, le=2048),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not files or len(files) > settings.DIOR_MAX_BATCH_IMAGES:
        raise DomainError(
            400,
            "INVALID_BATCH_SIZE",
            f"每批必须上传 1 至 {settings.DIOR_MAX_BATCH_IMAGES} 张图片",
        )
    validated_images: list[ValidatedImage] = []
    try:
        for file in files:
            validated_images.append(await validate_upload(file))
        return facility_detection_service.detect(
            db, current_user.id, validated_images, conf, iou, image_size
        )
    finally:
        for validated in validated_images:
            validated.cleanup()

