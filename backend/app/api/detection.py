"""Authenticated DIOR facility-detection endpoints."""

import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
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


@router.post("/video")
async def detect_video(
    file: Annotated[UploadFile, File(...)],
    frame_sample_rate: int = Form(default=5, ge=1, le=300),
    max_frames: int = Form(default=30, ge=1, le=100),
    conf: float = Form(default=settings.DIOR_CONF_THRESHOLD, ge=0.01, le=1.0),
    iou: float = Form(default=settings.DIOR_IOU_THRESHOLD, ge=0.01, le=1.0),
    image_size: int = Form(default=settings.DIOR_INPUT_SIZE, ge=320, le=2048),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sample an uploaded video and run DIOR detection on selected frames."""
    suffix = os.path.splitext(file.filename or "video.mp4")[1] or ".mp4"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            while chunk := await file.read(1024 * 1024):
                tmp.write(chunk)
        return facility_detection_service.detect_video(
            db=db,
            user_id=current_user.id,
            video_path=tmp_path,
            original_filename=file.filename or "video.mp4",
            conf=conf,
            iou=iou,
            image_size=image_size,
            frame_sample_rate=frame_sample_rate,
            max_frames=max_frames,
        )
    finally:
        await file.close()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

