"""Chat and shortcut segmentation API routes.

Routes:
  - POST /api/chat/upload      Upload an image file and return a safe reference.
  - POST /api/chat/stream      SSE streaming chat with the detection agent.
  - POST /api/segmentation/single   Shortcut single-image segmentation.
  - POST /api/segmentation/batch    Shortcut batch segmentation.
  - POST /api/segmentation/zip      Shortcut ZIP segmentation.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import tempfile
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
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
from app.services.agent_export_service import agent_export_service
from app.services.chat_image_reference_service import chat_image_reference_service
from app.services.detection_chat_service import detection_chat_service
from app.services.facility_detection_service import facility_detection_service
from app.utils.image_validation import ValidatedImage, validate_upload

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["智能对话"])
segmentation_router = APIRouter(prefix="/api/segmentation", tags=["快捷分割"])

_IMAGE_FOLLOW_UP = re.compile(
    r"(?:识别|检测|分析|分割|查看|看看|地物|类别|目标|东西|主要|有什么|有哪些)"
    r".*(?:图片|影像|图里|图例|图中|图上|刚才|刚刚|上传|这张|那张)|"
    r"(?:图片|影像|图里|图例|图中|图上|刚才|刚刚|上传|这张|那张)"
    r".*(?:识别|检测|分析|分割|查看|看看|地物|类别|目标|东西|主要|有什么|有哪些)"
)
_SHORT_IMAGE_COMMAND = re.compile(
    r"^(?:帮我)?(?:再)?(?:识别|检测|分析|查看|看看|分割|语义分割)"
    r"(?:一?下|一下吧|看看)?[。！!？?]*$"
)


def _save_chat_image(user_id: int, filename: str, content: bytes) -> str:
    return chat_image_reference_service.save(user_id, filename, BytesIO(content))


def _persistent_segmentation_result(result: dict, user_id: int) -> dict:
    """将结果中的大体积 base64 图片落盘，数据库只保存安全引用。"""
    persisted = copy.deepcopy(result)

    annotated_image = persisted.pop("annotated_image", None)
    if annotated_image:
        persisted["annotated_image_ref"] = _save_chat_image(
            user_id, "segmentation-result.jpg", base64.b64decode(annotated_image)
        )

    for image in persisted.get("annotated_images") or []:
        encoded = image.pop("annotated_image", None)
        if encoded:
            image["annotated_image_ref"] = _save_chat_image(
                user_id,
                f"{os.path.splitext(image.get('filename') or 'result')[0]}-segmented.jpg",
                base64.b64decode(encoded),
            )

    return persisted


def _prepare_facility_chat_result(result: dict, user_id: int) -> dict:
    """把 DIOR 标注图保存为会话安全引用，同时保留本轮可直接展示的 URL。"""
    storage = facility_detection_service._storage_client()
    for index, image in enumerate(result.get("images") or []):
        image.pop("source_object_key", None)
        annotated_key = image.pop("annotated_object_key", None)
        if not annotated_key:
            continue
        try:
            content = storage.read_bytes(annotated_key)
            stem = os.path.splitext(image.get("filename") or f"image-{index + 1}")[0]
            image["annotated_image_ref"] = _save_chat_image(
                user_id, f"{stem}-dior.jpg", content
            )
        except Exception:
            logger.warning("Could not persist batch DIOR result image", exc_info=True)
    result["kind"] = "facility_detection"
    return result


def _persistent_facility_result(result: dict) -> dict:
    """移除临时签名 URL；历史消息通过 annotated_image_ref 重新取图。"""
    persisted = copy.deepcopy(result)
    for image in persisted.get("images") or []:
        image.pop("source_url", None)
        image.pop("annotated_image_url", None)
        image.pop("source_object_key", None)
        image.pop("annotated_object_key", None)
    return persisted


def _merge_detection_tool_result(
    current: str | None,
    result_kind: str,
    payload: dict,
) -> str:
    """Keep both model results in one ChatMessage without breaking old records."""
    if not current:
        return json.dumps(payload, ensure_ascii=False)
    try:
        previous = json.loads(current)
    except (TypeError, json.JSONDecodeError):
        previous = None
    if not isinstance(previous, dict):
        return json.dumps(payload, ensure_ascii=False)
    if previous.get("kind") == "combined_detection":
        combined = previous
    elif previous.get("kind") == "facility_detection":
        combined = {"kind": "combined_detection", "facility_detection": previous}
    else:
        combined = {"kind": "combined_detection", "semantic": previous}
    combined[result_kind] = payload
    return json.dumps(combined, ensure_ascii=False)


def _requests_session_image(message: str) -> bool:
    """判断本轮是否明确要求处理会话中的最近图片。"""
    stripped = message.strip()
    if any(prefix in stripped for prefix in ("什么是", "解释一下", "介绍一下")):
        return False
    return (
        bool(_IMAGE_FOLLOW_UP.search(stripped))
        or bool(_SHORT_IMAGE_COMMAND.fullmatch(stripped))
        or "进行语义分割" in stripped
    )


@router.post("/upload", response_model=ChatUploadResponse, summary="上传图片文件")
async def upload_image(
    file: UploadFile = File(..., description="图片文件"),
    current_user: User = Depends(get_current_user),
):
    """保存到用户隔离目录，只返回不含路径的随机引用。"""
    try:
        image_ref = chat_image_reference_service.save(
            current_user.id, file.filename, file.file
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "Chat image uploaded: user_id=%s filename=%s ref=%s",
        current_user.id,
        file.filename,
        image_ref,
    )
    return {"image_ref": image_ref}


@router.get("/images/{image_ref}", summary="读取会话持久化图片")
def get_chat_image(
    image_ref: str,
    current_user: User = Depends(get_current_user),
):
    try:
        path = chat_image_reference_service.resolve(current_user.id, image_ref)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话图片不存在或已过期") from exc
    return FileResponse(path=path)


def _not_found(exc: SessionAccessError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/exports/{filename}", summary="下载 Agent 生成的数据文件")
def download_agent_export(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """仅允许当前用户下载自己目录中的 JSON/CSV 文件。"""
    try:
        path = agent_export_service.resolve(current_user.id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="导出文件不存在") from exc
    media_type = "text/csv" if path.suffix == ".csv" else "application/json"
    return FileResponse(path=path, media_type=media_type, filename=path.name)


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

    Accepts JSON body: { message, image_ref?, session_id? }
    """
    try:
        body = await request.json()
        payload = ChatStreamRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"请求体解析失败: {exc}") from exc

    if not payload.message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    image_path: str | None = None
    explicit_image_ref: str | None = None
    try:
        if payload.image_ref:
            explicit_image_ref = payload.image_ref.strip().lower()
            image_path = str(
                chat_image_reference_service.resolve(
                    _current_user.id, explicit_image_ref
                )
            )
        elif payload.image_path:
            explicit_image_ref = chat_image_reference_service.reference_for_path(
                _current_user.id, payload.image_path
            )
            image_path = str(
                chat_image_reference_service.resolve(
                    _current_user.id, explicit_image_ref
                )
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail="图片引用无效或不属于当前用户") from exc
    try:
        session, _created = chat_session_service.get_or_create(
            db, _current_user.id, payload.session_id, payload.message
        )
    except SessionAccessError as exc:
        raise _not_found(exc) from exc

    if explicit_image_ref:
        session.last_image_ref = explicit_image_ref
        db.commit()
    elif _requests_session_image(payload.message) and session.last_image_ref:
        try:
            image_path = str(
                chat_image_reference_service.resolve(
                    _current_user.id, session.last_image_ref
                )
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=410, detail="会话中的图片已过期，请重新上传"
            ) from exc

    logger.info(
        "User %s chat: message=%s has_image=%s",
        _current_user.username,
        payload.message[:50],
        bool(image_path),
    )

    async def event_generator():
        assistant_parts: list[str] = []
        route = "chat"
        tool_calls: list[dict] = []
        persisted_tool_result: str | None = None
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
                elif event.get("type") == "tool_result":
                    try:
                        parsed_result = json.loads(str(event.get("result", "")))
                        if (
                            parsed_result.get("class_statistics")
                            or parsed_result.get("annotated_images")
                            or parsed_result.get("annotated_image")
                        ) and parsed_result.get("kind") != "facility_detection":
                            persisted_tool_result = _merge_detection_tool_result(
                                persisted_tool_result,
                                "semantic",
                                _persistent_segmentation_result(
                                    parsed_result, _current_user.id
                                ),
                            )
                        elif parsed_result.get("kind") == "facility_detection":
                            persisted = copy.deepcopy(parsed_result)
                            for image in persisted.get("images") or []:
                                image.pop("source_url", None)
                                image.pop("annotated_image_url", None)
                            persisted_tool_result = _merge_detection_tool_result(
                                persisted_tool_result,
                                "facility_detection",
                                persisted,
                            )
                        elif route == "export" and parsed_result.get("filename") and parsed_result.get("download_url"):
                            persisted_tool_result = json.dumps(
                                {
                                    key: parsed_result.get(key)
                                    for key in (
                                        "filename",
                                        "format",
                                        "data_type",
                                        "size_bytes",
                                        "download_url",
                                    )
                                },
                                ensure_ascii=False,
                            )
                    except (TypeError, json.JSONDecodeError):
                        persisted_tool_result = None
                elif event.get("type") == "error":
                    stream_failed = True
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            assistant_text = "".join(assistant_parts).strip()
            if not stream_failed and assistant_text:
                chat_session_service.save_turn(
                    db,
                    session,
                    payload.message,
                    assistant_text,
                    route,
                    tool_calls,
                    persisted_tool_result,
                    (
                        [{"filename": "上传图片", "image_ref": explicit_image_ref}]
                        if explicit_image_ref
                        else None
                    ),
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
    content = file.file.read()
    original_ref = _save_chat_image(current_user.id, file.filename or f"image{suffix}", content)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
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
            chat_session_service.save_turn(
                db,
                session,
                "[快捷分割] 单图",
                summary,
                "detection",
                [{"tool": "segment_single"}],
                json.dumps(
                    _persistent_segmentation_result(result, current_user.id),
                    ensure_ascii=False,
                ),
                [{"filename": file.filename or "image", "image_ref": original_ref}],
            )
            chat_memory_service.append_turn(current_user.id, session.session_uuid, "[快捷分割] 单图", summary, "detection")
            result["session_id"] = session.id
        return result
    finally:
        os.unlink(tmp_path)


@segmentation_router.post(
    "/batch", response_model=SegmentationBatchResponse, summary="批量联合检测"
)
async def segment_batch_api(
    files: list[UploadFile] = File(..., description="多张待分割图片"),
    conf: float = Form(
        0.25, description="置信度阈值（语义分割中保留参数，当前未使用）"
    ),
    scene_id: int = Form(None, description="场景 ID"),
    session_id: int = Form(None, description="当前会话 ID"),
    message: str = Form(None, description="用户在对话框中输入的原始消息"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run LoveDA segmentation and DIOR facility detection on the same image batch."""
    temp_paths: list[str] = []
    validated_images: list[ValidatedImage] = []
    original_attachments: list[dict] = []
    try:
        for upload in files:
            validated = await validate_upload(upload)
            validated_images.append(validated)
            content = validated.temp_path.read_bytes()
            original_ref = _save_chat_image(
                current_user.id, validated.original_filename, content
            )
            original_attachments.append(
                {"filename": validated.original_filename, "image_ref": original_ref}
            )
            temp_paths.append(str(validated.temp_path))

        result = detection_chat_service.segment_batch(
            image_paths=temp_paths,
            user_id=current_user.id,
            scene_id=scene_id,
        )
        facility_result: dict | None = None
        facility_error: str | None = None
        if len(validated_images) > settings.DIOR_MAX_BATCH_IMAGES:
            facility_error = (
                f"DIOR 每批最多支持 {settings.DIOR_MAX_BATCH_IMAGES} 张图片"
            )
        elif not facility_detection_service.runtime.ready:
            facility_error = "DIOR 检测模型当前不可用"
        else:
            try:
                facility_result = facility_detection_service.detect(
                    db,
                    current_user.id,
                    validated_images,
                    settings.DIOR_CONF_THRESHOLD,
                    settings.DIOR_IOU_THRESHOLD,
                    settings.DIOR_INPUT_SIZE,
                    include_object_keys=True,
                )
                facility_result = _prepare_facility_chat_result(
                    facility_result, current_user.id
                )
                result["facility_detection"] = facility_result
            except Exception as exc:
                logger.exception(
                    "Batch DIOR detection failed: exception_type=%s",
                    type(exc).__name__,
                )
                facility_error = "DIOR 设施检测失败，LoveDA 分割结果仍可用"
        if facility_error:
            result["facility_detection_error"] = facility_error

        if session_id is not None:
            try:
                session = chat_session_service.owned(db, current_user.id, session_id)
            except SessionAccessError as exc:
                raise _not_found(exc) from exc
            summary = _segmentation_summary(result, "批量分割")
            if facility_result is not None:
                display_summary = (
                    f"联合检测完成！LoveDA 已处理 {result.get('successful_images', 0)} 张图片，"
                    f"DIOR 共检测到 {facility_result.get('total_objects', 0)} 个设施目标。"
                )
            else:
                display_summary = (
                    f"LoveDA 批量分割完成，共 {result.get('successful_images', 0)} 张图片；"
                    f"{facility_error or 'DIOR 未返回结果'}。"
                )
            semantic_payload = {
                key: value
                for key, value in result.items()
                if key not in {"facility_detection", "facility_detection_error"}
            }
            semantic_persisted = _persistent_segmentation_result(
                semantic_payload, current_user.id
            )
            persisted_tool_result = json.dumps(
                semantic_persisted, ensure_ascii=False
            )
            if facility_result is not None:
                persisted_tool_result = _merge_detection_tool_result(
                    json.dumps(semantic_persisted, ensure_ascii=False),
                    "facility_detection",
                    _persistent_facility_result(facility_result),
                )
            chat_session_service.save_turn(
                db,
                session,
                message or f"[快捷分割] {len(files)} 张图片",
                display_summary,
                "combined_detection" if facility_result is not None else "detection",
                [
                    {"tool": "segment_batch"},
                    {"tool": "detect_dior_facilities"},
                ]
                if facility_result is not None
                else [{"tool": "segment_batch"}],
                persisted_tool_result,
                original_attachments,
            )
            chat_memory_service.append_turn(
                current_user.id,
                session.session_uuid,
                message or "[快捷分割] 批量图片",
                summary,
                "combined_detection" if facility_result is not None else "detection",
            )
            result["session_id"] = session.id
        return result
    finally:
        for validated in validated_images:
            validated.cleanup()


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
            chat_session_service.save_turn(
                db,
                session,
                "[快捷分割] ZIP",
                summary,
                "detection",
                [{"tool": "segment_zip"}],
                json.dumps(
                    _persistent_segmentation_result(result, current_user.id),
                    ensure_ascii=False,
                ),
            )
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
