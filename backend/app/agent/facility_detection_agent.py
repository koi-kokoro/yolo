"""Deterministic DIOR facility-detection agent."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncGenerator

from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.services.facility_detection_service import facility_detection_service
from app.services.chat_image_reference_service import chat_image_reference_service

logger = get_logger(__name__)


def _summary(result: dict[str, Any]) -> str:
    total = int(result.get("total_objects") or 0)
    statistics = result.get("class_statistics") or []
    if not statistics:
        return "DIOR 设施检测已完成，当前置信度阈值下未发现目标。你可以适当降低阈值后重新检测。"
    detail = "、".join(
        f"{item.get('class_name_cn') or item.get('class_name')} {item.get('count', 0)} 个"
        for item in statistics[:8]
    )
    return f"DIOR 设施检测已完成，共发现 {total} 个目标：{detail}。检测框和置信度已保存到历史记录。"


class FacilityDetectionAgent:
    async def chat_stream(
        self,
        message: str,
        image_path: str | None = None,
        user_id: int | None = None,
        scene_id: int | None = None,
        memory: list[dict[str, str]] | None = None,
        workflow_state: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        del message, scene_id, memory, workflow_state
        if not image_path:
            yield {"type": "text_chunk", "content": "请在当前消息中上传遥感图片，我会使用 DIOR 检测设施目标。"}
            return
        if user_id is None:
            yield {"type": "error", "content": "当前用户信息不可用，无法保存设施检测结果。"}
            return

        yield {
            "type": "tool_call",
            "tool": "detect_dior_facilities",
            "input": {"image": "[当前会话上传图片]"},
        }
        db = SessionLocal()
        try:
            result = facility_detection_service.detect_local_file(
                db, user_id, image_path, include_object_keys=True
            )
        except Exception as exc:
            logger.exception("DIOR facility agent inference failed: %s", type(exc).__name__)
            yield {"type": "error", "content": "DIOR 设施检测失败，请检查模型状态和上传图片后重试。"}
            return
        finally:
            db.close()

        storage = facility_detection_service._storage_client()
        for index, image in enumerate(result.get("images") or []):
            image.pop("source_object_key", None)
            annotated_key = image.pop("annotated_object_key", None)
            if annotated_key:
                try:
                    content = storage.read_bytes(annotated_key)
                    stem = Path(image.get("filename") or f"image-{index + 1}").stem
                    image["annotated_image_ref"] = chat_image_reference_service.save(
                        user_id,
                        f"{stem}-dior.jpg",
                        BytesIO(content),
                    )
                except Exception:
                    logger.warning("Could not persist DIOR chat result image", exc_info=True)
        result["kind"] = "facility_detection"
        yield {
            "type": "tool_result",
            "tool": "detect_dior_facilities",
            "result": json.dumps(result, ensure_ascii=False),
        }
        yield {"type": "text_chunk", "content": _summary(result)}


facility_detection_agent = FacilityDetectionAgent()
