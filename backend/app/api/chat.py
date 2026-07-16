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
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import get_db
from app.entity.db_models import User
from app.entity.schemas import (
    ChatMessagePage,
    ChatSessionCreate,
    ChatSessionPage,
    ChatSessionRename,
    ChatSessionResponse,
    ChatStreamRequest,
    ChatUploadResponse,
    SegmentationBatchResponse,
    SegmentationSingleResponse,
)
from app.orchestration.orchestrator import orchestrator
from app.services.chat_session_service import (
    SessionAccessError,
    chat_memory_service,
    chat_session_service,
)
from app.services.detection_chat_service import detection_chat_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["智能对话"])
segmentation_router = APIRouter(prefix="/api/segmentation", tags=["快捷分割"])

UPLOAD_DIR = settings.chat_upload_path
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_ALLOWED_UPLOAD_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def _save_upload(file: UploadFile) -> str:
    """以服务端随机名保存，阻止目录穿越与同名覆盖。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持的图片扩展名")
    file_path = (UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}").resolve()
    with file_path.open("xb") as handle:
        handle.write(file.file.read())
    return str(file_path)


def _trusted_image_path(value: str | None) -> str | None:
    if not value:
        return None
    resolved = Path(value).resolve(strict=False)
    trusted = UPLOAD_DIR.resolve()
    if trusted not in resolved.parents or not resolved.is_file():
        raise HTTPException(status_code=400, detail="image_path 不在受信任上传目录")
    return str(resolved)


@router.post("/upload", response_model=ChatUploadResponse, summary="上传图片文件")
async def upload_image(
    file: UploadFile = File(..., description="图片文件"),
    _current_user: User = Depends(get_current_user),
):
    """Upload an image file to the server temp directory."""
    file_path = _save_upload(file)
    logger.info("Image uploaded: %s -> %s", file.filename, file_path)
    return {"image_path": file_path}


def _not_found(exc: SessionAccessError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions", response_model=ChatSessionResponse, status_code=201)
def create_session(
    payload: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_session_service.create(db, current_user.id, payload.title)


@router.get("/sessions", response_model=ChatSessionPage)
def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = chat_session_service.list_sessions(db, current_user.id, page, page_size)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return chat_session_service.owned(db, current_user.id, session_id)
    except SessionAccessError as exc:
        raise _not_found(exc) from exc


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
def rename_session(
    session_id: int,
    payload: ChatSessionRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return chat_session_service.rename(db, current_user.id, session_id, payload.title)
    except SessionAccessError as exc:
        raise _not_found(exc) from exc


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        chat_session_service.delete(db, current_user.id, session_id)
    except SessionAccessError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=204)


@router.get("/sessions/{session_id}/messages", response_model=ChatMessagePage)
def list_messages(
    session_id: int,
    limit: int = Query(30, ge=1, le=100),
    before_id: int | None = Query(None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        items, next_cursor, has_more = chat_session_service.messages(
            db, current_user.id, session_id, limit, before_id
        )
    except SessionAccessError as exc:
        raise _not_found(exc) from exc
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


@router.post("/stream", summary="SSE 流式对话")
async def chat_stream(
    request: Request,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    image_path = _trusted_image_path(payload.image_path)
    try:
        session, _created = chat_session_service.get_or_create(
            db, _current_user.id, payload.session_id, payload.message
        )
    except SessionAccessError as exc:
        raise _not_found(exc) from exc

    logger.info(
        "User %s chat: message=%s has_image=%s",
        _current_user.username,
        payload.message[:50],
        bool(payload.image_path),
    )

    async def event_generator():
        assistant_parts: list[str] = []
        route = "chat"
        tool_calls: list[dict] = []
        stream_failed = False
        try:
            # 每次发送，便于前端确认请求实际绑定的会话。
            yield f"data: {json.dumps({'type': 'session', 'session_id': session.id, 'session_uuid': session.session_uuid}, ensure_ascii=False)}\n\n"
            memory = chat_session_service.load_memory(db, _current_user.id, session)
            async for event in orchestrator.chat_stream(
                message=payload.message,
                image_path=image_path,
                user_id=_current_user.id,
                scene_id=payload.scene_id,
                memory=memory,
            ):
                if event.get("type") == "agent_route":
                    route = event.get("agent", "chat")
                elif event.get("type") == "text_chunk":
                    assistant_parts.append(str(event.get("content", "")))
                elif event.get("type") == "tool_call":
                    tool_calls.append({"tool": event.get("tool"), "input": event.get("input")})
                elif event.get("type") == "error":
                    stream_failed = True
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            assistant_text = "".join(assistant_parts).strip()
            if not stream_failed and assistant_text:
                chat_session_service.save_turn(
                    db, session, payload.message, assistant_text, route, tool_calls
                )
                chat_memory_service.append_turn(
                    _current_user.id,
                    session.session_uuid,
                    payload.message,
                    assistant_text,
                    route,
                )
            yield "data: [DONE]\n\n"
        except Exception as exc:
            db.rollback()
            logger.error("SSE stream error: %s", exc, exc_info=True)
            error_data = json.dumps(
                {"type": "error", "content": "对话处理失败"}, ensure_ascii=False
            )
            yield f"data: {error_data}\n\n"
            yield "data: [DONE]\n\n"

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
    session_id: int = Form(None, description="当前会话 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
        if session_id is not None:
            try:
                session = chat_session_service.owned(db, current_user.id, session_id)
            except SessionAccessError as exc:
                raise _not_found(exc) from exc
            summary = _segmentation_summary(result, "单图分割")
            chat_session_service.save_turn(db, session, "[快捷分割] 单图", summary, "detection", [{"tool": "segment_single"}])
            chat_memory_service.append_turn(current_user.id, session.session_uuid, "[快捷分割] 单图", summary, "detection")
            result["session_id"] = session.id
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
    session_id: int = Form(None, description="当前会话 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
        if session_id is not None:
            try:
                session = chat_session_service.owned(db, current_user.id, session_id)
            except SessionAccessError as exc:
                raise _not_found(exc) from exc
            summary = _segmentation_summary(result, "批量分割")
            chat_session_service.save_turn(db, session, f"[快捷分割] {len(files)} 张图片", summary, "detection", [{"tool": "segment_batch"}])
            chat_memory_service.append_turn(current_user.id, session.session_uuid, "[快捷分割] 批量图片", summary, "detection")
            result["session_id"] = session.id
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
    session_id: int = Form(None, description="当前会话 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
        if session_id is not None:
            try:
                session = chat_session_service.owned(db, current_user.id, session_id)
            except SessionAccessError as exc:
                raise _not_found(exc) from exc
            summary = _segmentation_summary(result, "ZIP 分割")
            chat_session_service.save_turn(db, session, "[快捷分割] ZIP", summary, "detection", [{"tool": "segment_zip"}])
            chat_memory_service.append_turn(current_user.id, session.session_uuid, "[快捷分割] ZIP", summary, "detection")
            result["session_id"] = session.id
        return result
    finally:
        os.unlink(tmp_path)


def _segmentation_summary(result: dict, label: str) -> str:
    """只保留可追问的规范化文本统计，不保存 base64、路径或完整结果。"""
    counts = result.get("class_counts") or {
        item.get("display_name") or item.get("name"): item.get("pixel_count", 0)
        for item in result.get("class_statistics", [])
        if item.get("display_name") or item.get("name")
    }
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    total = result.get("successful_images") or result.get("total_images") or 1
    return f"{label}完成，共处理 {total} 张；主要地物：" + "、".join(
        f"{name}({count})" for name, count in top
    )


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
