"""Chat and shortcut segmentation API routes.

Routes:
  - POST /api/chat/upload      Upload an image file and return server path.
  - POST /api/chat/stream      SSE streaming chat with the detection agent.
  - POST /api/segmentation/single   Shortcut single-image segmentation.
  - POST /api/segmentation/batch    Shortcut batch segmentation.
  - POST /api/segmentation/zip      Shortcut ZIP segmentation.
"""

from __future__ import annotations

import json
import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.agent.detection_agent import detection_agent
from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.entity.db_models import User
from app.entity.schemas import (
    ChatStreamRequest,
    ChatUploadResponse,
    SegmentationBatchResponse,
    SegmentationSingleResponse,
)
from app.services.detection_chat_service import detection_chat_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["智能对话"])
segmentation_router = APIRouter(prefix="/api/segmentation", tags=["快捷分割"])

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "detection_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _save_upload(file: UploadFile) -> str:
    """Save an uploaded file to the temp upload directory and return its path."""
    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"{os.getpid()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as handle:
        handle.write(file.file.read())
    return file_path


@router.post("/upload", response_model=ChatUploadResponse, summary="上传图片文件")
async def upload_image(
    file: UploadFile = File(..., description="图片文件"),
    _current_user: User = Depends(get_current_user),
):
    """Upload an image file to the server temp directory."""
    file_path = _save_upload(file)
    logger.info("Image uploaded: %s -> %s", file.filename, file_path)
    return {"image_path": file_path}


@router.post("/stream", summary="SSE 流式对话")
async def chat_stream(
    request: Request,
    _current_user: User = Depends(get_current_user),
):
    """SSE streaming chat endpoint.

    Accepts JSON body: { message, image_path?, session_id? }
    """
    try:
        body = await request.json()
        payload = ChatStreamRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"请求体解析失败: {exc}") from exc

    if not payload.message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    logger.info(
        "User %s chat: message=%s has_image=%s",
        _current_user.username,
        payload.message[:50],
        bool(payload.image_path),
    )

    async def event_generator():
        try:
            async for event in detection_agent.chat_stream(
                message=payload.message,
                image_path=payload.image_path,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("SSE stream error: %s", exc, exc_info=True)
            error_data = json.dumps(
                {"type": "error", "content": str(exc)}, ensure_ascii=False
            )
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@segmentation_router.post(
    "/single", response_model=SegmentationSingleResponse, summary="单图语义分割"
)
async def segment_single_api(
    file: UploadFile = File(..., description="待分割图片"),
    conf: float = Form(
        0.25, description="置信度阈值（语义分割中保留参数，当前未使用）"
    ),
    scene_id: int = Form(None, description="场景 ID"),
    current_user: User = Depends(get_current_user),
):
    """Shortcut single-image semantic segmentation (bypasses LLM)."""
    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        result = detection_chat_service.segment_single(
            image_path=tmp_path,
            user_id=current_user.id,
            scene_id=scene_id,
        )
        return result
    finally:
        os.unlink(tmp_path)


@segmentation_router.post(
    "/batch", response_model=SegmentationBatchResponse, summary="批量语义分割"
)
async def segment_batch_api(
    files: list[UploadFile] = File(..., description="多张待分割图片"),
    conf: float = Form(
        0.25, description="置信度阈值（语义分割中保留参数，当前未使用）"
    ),
    scene_id: int = Form(None, description="场景 ID"),
    current_user: User = Depends(get_current_user),
):
    """Shortcut batch semantic segmentation (bypasses LLM)."""
    temp_paths: list[str] = []
    try:
        for upload in files:
            suffix = os.path.splitext(upload.filename)[1] or ".jpg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(upload.file.read())
                temp_paths.append(tmp.name)

        result = detection_chat_service.segment_batch(
            image_paths=temp_paths,
            user_id=current_user.id,
            scene_id=scene_id,
        )
        return result
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except Exception:
                pass


@segmentation_router.post(
    "/zip", response_model=SegmentationBatchResponse, summary="ZIP 语义分割"
)
async def segment_zip_api(
    file: UploadFile = File(..., description="包含图片的 ZIP 压缩包"),
    conf: float = Form(
        0.25, description="置信度阈值（语义分割中保留参数，当前未使用）"
    ),
    scene_id: int = Form(None, description="场景 ID"),
    current_user: User = Depends(get_current_user),
):
    """Shortcut ZIP semantic segmentation (bypasses LLM)."""
    suffix = os.path.splitext(file.filename)[1] or ".zip"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        result = detection_chat_service.segment_zip(
            zip_path=tmp_path,
            user_id=current_user.id,
            scene_id=scene_id,
        )
        return result
    finally:
        os.unlink(tmp_path)


@segmentation_router.post("/video", summary="视频语义分割")
async def segment_video_api(
    file: UploadFile = File(..., description="待分割视频"),
    frame_sample_rate: int = Form(5, description="采样间隔帧数"),
    max_frames: int = Form(50, description="最多采样帧数"),
    scene_id: int = Form(None, description="场景 ID"),
    current_user: User = Depends(get_current_user),
):
    """Shortcut video semantic segmentation (sample key frames)."""
    suffix = os.path.splitext(file.filename)[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        return detection_chat_service.detect_video(
            video_path=tmp_path,
            frame_sample_rate=frame_sample_rate,
            max_frames=max_frames,
            user_id=current_user.id,
            scene_id=scene_id,
        )
    finally:
        os.unlink(tmp_path)
