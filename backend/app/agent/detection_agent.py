"""Detection agent — ReAct Agent + image analysis tools.

Responsibilities:
  - Create a LangChain agent using the langchain 1.x create_agent factory.
  - Bind image analysis tools (single / batch / ZIP).
  - Stream Agent thoughts and results for the chat SSE endpoint.

Usage:
  from app.agent.detection_agent import detection_agent
  result = await detection_agent.chat("分析这张图片", image_path="xxx.jpg")
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from langchain.agents import create_agent
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.config.settings import settings
from app.core.logger import get_logger
from app.services.detection_chat_service import (
    detection_chat_service,
    get_or_create_default_scene,
)

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════
# 一、定义图像检测工具（Agent 可调用的 Tools）
# ══════════════════════════════════════════════════════════════

# Keys whose values are base64 image data that must not be fed back into the
# LLM context window; otherwise model APIs reject the request for being too long.
_IMAGE_DATA_KEYS = {
    "base64",
    "annotated_image",
    "annotated_image_base64",
    "annotated_image_bytes",
}

# Cache raw tool results so the full payload (including annotated images) can be
# forwarded to the chat UI while the LLM only sees a compact summary.
_TOOL_RESULT_CACHE: dict[str, Any] = {}


def _strip_image_data(obj: Any) -> Any:
    """Recursively replace image base64 fields with a placeholder."""
    if isinstance(obj, dict):
        return {
            key: (
                "[Image data omitted from LLM context]"
                if key in _IMAGE_DATA_KEYS
                else _strip_image_data(value)
            )
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_strip_image_data(item) for item in obj]
    return obj


def _tool_result_cache_key(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Build a deterministic cache key from a tool name and its input."""
    if tool_name == "segment_single_image":
        return f"single:{tool_input.get('image_path', '')}"
    if tool_name == "segment_batch_images":
        paths = tool_input.get("image_paths", [])
        return f"batch:{','.join(str(path) for path in paths)}"
    if tool_name == "segment_zip_file":
        return f"zip:{tool_input.get('zip_path', '')}"
    return f"{tool_name}:{json.dumps(tool_input, sort_keys=True, ensure_ascii=False)}"


@tool
def segment_single_image(image_path: str) -> str:
    """
    对单张图片进行 LoveDA 7 类语义分割。

    Args:
        image_path: 图片文件路径或 URL

    Returns:
        JSON 字符串，包含分割结果（已去除图像 base64 数据，防止 LLM 上下文过长）
    """
    import os

    print(f"--- [Debug] Checking file path: {image_path} ---")
    print(f"--- [Debug] File exists: {os.path.exists(image_path)} ---")
    if os.path.exists(image_path):
        print(f"--- [Debug] File size: {os.path.getsize(image_path)} bytes ---")

    raw_result = detection_chat_service.segment_single(image_path)
    cache_key = _tool_result_cache_key(
        "segment_single_image", {"image_path": image_path}
    )
    _TOOL_RESULT_CACHE[cache_key] = raw_result
    cleaned_result = _strip_image_data(raw_result)

    return json.dumps(cleaned_result, ensure_ascii=False)


@tool
def segment_batch_images(image_paths: list[str]) -> str:
    """
    对多张图片批量进行语义分割。

    Args:
        image_paths: 图片文件路径列表

    Returns:
        JSON 字符串，包含每张图片的分割结果汇总（已去除图像 base64 数据）
    """
    raw_result = detection_chat_service.segment_batch(image_paths)
    cache_key = _tool_result_cache_key(
        "segment_batch_images", {"image_paths": image_paths}
    )
    _TOOL_RESULT_CACHE[cache_key] = raw_result
    cleaned_result = _strip_image_data(raw_result)

    return json.dumps(cleaned_result, ensure_ascii=False)


@tool
def segment_zip_file(zip_path: str) -> str:
    """
    解压 ZIP 文件并批量分割其中所有图片。

    Args:
        zip_path: ZIP 文件路径

    Returns:
        JSON 字符串，包含 ZIP 内所有图片的分割结果汇总（已去除图像 base64 数据）
    """
    raw_result = detection_chat_service.segment_zip(zip_path)
    cache_key = _tool_result_cache_key("segment_zip_file", {"zip_path": zip_path})
    _TOOL_RESULT_CACHE[cache_key] = raw_result
    cleaned_result = _strip_image_data(raw_result)

    return json.dumps(cleaned_result, ensure_ascii=False)


DETECTION_TOOLS = [segment_single_image, segment_batch_images, segment_zip_file]


# ══════════════════════════════════════════════════════════════
# 二、创建 LLM 实例
# ══════════════════════════════════════════════════════════════


def _create_llm() -> ChatOpenAI:
    """Create an LLM instance according to configuration."""
    qwen_api_key = getattr(settings, "QWEN_API_KEY", "")
    if qwen_api_key and qwen_api_key != "sk-your-qwen-api-key":
        api_key = qwen_api_key
        base_url = getattr(
            settings,
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        model_name = getattr(settings, "QWEN_MODEL", "qwen-plus")
    else:
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        base_url = getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")
        model_name = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
    )


# ══════════════════════════════════════════════════════════════
# 三、创建 Agent
# ══════════════════════════════════════════════════════════════


_SYSTEM_PROMPT = """你是一个专业的遥感检测助手。你可以帮用户对图片进行 LoveDA 7 类分析。

重要规则：
- 当用户消息中包含 [附件图片路径: xxx] 时，xxx 就是图片的服务器路径，你应直接使用它调用分析工具
- 不要要求用户再次提供路径，直接使用附件中给出的路径
- 对于单张图片，调用 segment_single_image 工具
- 对于多张图片或 ZIP 文件，调用 segment_batch_images 或 segment_zip_file 工具

工作流程：
1. 理解用户意图
2. 如果有附件图片路径，直接调用分析工具
3. 调用工具获取分析结果
4. 用自然语言总结分析结果

回复格式要求：
- 单张图片：报告图片尺寸、各类别像素数量与占比，并指出主要地物。
- 多张图片或 ZIP：工具结果中已提供 `agent_response` 字段（含逐图摘要），请直接依据该字段组织回复，确保按图片文件名逐一分析，分别报告每张图片的尺寸、主要类别及像素占比。禁止只给出合并后的总统计。
- 逐张分析后可给一句简要的总体对比或汇总（可选）。
- 如果有标注图，告知用户可以在结果卡片中查看。
- 简洁专业，不要过度解释"""


class DetectionAgent:
    """Detection agent — wraps agent creation and chat logic."""

    def __init__(self) -> None:
        self.llm = _create_llm()
        self.executor = create_agent(
            model=self.llm,
            tools=DETECTION_TOOLS,
            system_prompt=_SYSTEM_PROMPT,
        )
        logger.info("DetectionAgent initialized with %d tools", len(DETECTION_TOOLS))

    def _build_input(
        self, message: str, image_path: str | None = None
    ) -> dict[str, Any]:
        if image_path:
            message = f"{message}\n[附件图片路径: {image_path}]"
        return {"messages": [("human", message)]}

    async def chat(self, message: str, image_path: str | None = None) -> dict[str, Any]:
        """Process a user message (non-streaming)."""
        try:
            result = await self.executor.ainvoke(self._build_input(message, image_path))
            messages = result.get("messages", [])
            output = ""
            if messages:
                output = messages[-1].content
            return {"output": output, "messages": messages}
        except Exception as exc:
            logger.error("Agent execution error: %s", exc, exc_info=True)
            return {"output": f"抱歉，处理过程中出现错误：{exc}", "messages": []}

    async def chat_stream(
        self,
        message: str,
        image_path: str | None = None,
        user_id: int | None = None,
        scene_id: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Process a user message and yield SSE events."""
        try:
            async for event in self.executor.astream_events(
                self._build_input(message, image_path),
                version="v2",
            ):
                event_kind = event.get("event")

                if event_kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and getattr(chunk, "content", None):
                        yield {"type": "text_chunk", "content": chunk.content}

                elif event_kind == "on_tool_start":
                    tool_name = event.get("name")
                    tool_input = event.get("data", {}).get("input", {})
                    logger.info(
                        "Tool call: %s input=%s", tool_name, str(tool_input)[:200]
                    )
                    yield {"type": "tool_call", "tool": tool_name, "input": tool_input}

                elif event_kind == "on_tool_end":
                    tool_data = event.get("data", {})
                    tool_output = tool_data.get("output", "")
                    tool_name = event.get("name", "")
                    tool_input = tool_data.get("input", {})

                    # LangChain may hand us a ToolMessage object instead of a raw string.
                    if isinstance(tool_output, ToolMessage):
                        output_text = tool_output.content
                    else:
                        output_text = tool_output

                    logger.info(
                        "Tool done: %s output_type=%s output_len=%d",
                        tool_name,
                        type(tool_output).__name__,
                        len(str(output_text)) if output_text else 0,
                    )

                    # Send the original full result (with annotated images) to the
                    # chat UI, while the LLM only received the compact version.
                    cache_key = _tool_result_cache_key(tool_name, tool_input)
                    full_result = _TOOL_RESULT_CACHE.pop(cache_key, None)
                    if full_result is None:
                        client_payload = output_text
                    elif isinstance(full_result, str):
                        client_payload = full_result
                    else:
                        client_payload = json.dumps(full_result, ensure_ascii=False)

                    # Persist a lightweight DetectionTask from tool output
                    # when user_id is provided. Tool outputs are JSON strings from
                    # detection_chat_service.segment_* wrappers.
                    if user_id is not None and output_text:
                        try:
                            from datetime import datetime
                            from app.database.session import SessionLocal
                            from app.entity.db_models import (
                                DetectionTask,
                                DetectionScene,
                                User,
                            )

                            parsed = (
                                json.loads(output_text)
                                if isinstance(output_text, str)
                                else output_text
                            )
                            if isinstance(parsed, dict):
                                mode = parsed.get("mode")
                                db = SessionLocal()
                                try:
                                    user_exists = (
                                        db.query(User).filter(User.id == user_id).first()
                                    )
                                    if not user_exists:
                                        logger.warning(
                                            "Skip chat task persistence: user %s not found",
                                            user_id,
                                        )
                                    else:
                                        scene = None
                                        if scene_id is not None:
                                            scene = (
                                                db.query(DetectionScene)
                                                .filter(DetectionScene.id == scene_id)
                                                .first()
                                            )
                                        if scene is None:
                                            scene = get_or_create_default_scene(db, user_id)

                                        if scene is not None:
                                            if mode == "single":
                                                total_images = 1
                                                total_objects = sum(
                                                    item.get("pixel_count", 0)
                                                    for item in parsed.get(
                                                        "class_statistics", []
                                                    )
                                                )
                                                total_inference_time = float(
                                                    parsed.get("inference_time_ms") or 0.0
                                                )
                                            elif mode in {"batch", "zip"}:
                                                total_images = int(
                                                    parsed.get("total_images") or 0
                                                )
                                                total_objects = (
                                                    sum(
                                                        parsed.get(
                                                            "class_counts", {}
                                                        ).values()
                                                    )
                                                    if parsed.get("class_counts")
                                                    else 0
                                                )
                                                total_inference_time = float(
                                                    parsed.get("total_inference_ms") or 0.0
                                                )
                                            else:
                                                total_images = 0
                                                total_objects = 0
                                                total_inference_time = 0.0

                                            task = DetectionTask(
                                                user_id=user_id,
                                                scene_id=scene.id,
                                                task_type=mode or "chat",
                                                status="completed",
                                                total_images=total_images,
                                                total_objects=total_objects,
                                                total_inference_time=total_inference_time,
                                                completed_at=datetime.now(),
                                            )
                                            db.add(task)
                                            db.commit()
                                finally:
                                    db.close()
                        except Exception:
                            logger.exception(
                                "Failed to persist chat-triggered DetectionTask"
                            )

                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result": str(client_payload) if client_payload else "",
                    }

        except Exception as exc:
            logger.error("Agent stream error: %s", exc, exc_info=True)
            yield {"type": "error", "content": f"处理出错：{exc}"}


detection_agent = DetectionAgent()
