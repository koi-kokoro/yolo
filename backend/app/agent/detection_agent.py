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
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.config.settings import settings
from app.core.logger import get_logger
from app.services.detection_chat_service import detection_chat_service

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════
# 一、定义图像检测工具（Agent 可调用的 Tools）
# ══════════════════════════════════════════════════════════════


@tool
def segment_single_image(image_path: str) -> str:
    """
    对单张图片进行 LoveDA 7 类语义分割。

    Args:
        image_path: 图片文件路径或 URL

    Returns:
        JSON 字符串，包含分割结果（类别像素统计、标注图 base64）
    """
    result = detection_chat_service.segment_single(image_path)
    return json.dumps(result, ensure_ascii=False)


@tool
def segment_batch_images(image_paths: list[str]) -> str:
    """
    对多张图片批量进行语义分割。

    Args:
        image_paths: 图片文件路径列表

    Returns:
        JSON 字符串，包含每张图片的分割结果汇总
    """
    result = detection_chat_service.segment_batch(image_paths)
    return json.dumps(result, ensure_ascii=False)


@tool
def segment_zip_file(zip_path: str) -> str:
    """
    解压 ZIP 文件并批量分割其中所有图片。

    Args:
        zip_path: ZIP 文件路径

    Returns:
        JSON 字符串，包含 ZIP 内所有图片的分割结果汇总
    """
    result = detection_chat_service.segment_zip(zip_path)
    return json.dumps(result, ensure_ascii=False)


DETECTION_TOOLS = [segment_single_image, segment_batch_images, segment_zip_file]


# ══════════════════════════════════════════════════════════════
# 二、创建 LLM 实例
# ══════════════════════════════════════════════════════════════


def _create_llm() -> ChatOpenAI:
    """Create an LLM instance according to configuration."""
    qwen_api_key = getattr(settings, "QWEN_API_KEY", "")
    if qwen_api_key and qwen_api_key != "sk-your-qwen-api-key":
        api_key = qwen_api_key
        base_url = getattr(settings, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
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
- 先报告图片数量和总像素统计
- 列出各土地覆盖类别的像素占比
- 如果有标注图，告知用户可以在结果卡片中查看
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

    def _build_input(self, message: str, image_path: str | None = None) -> dict[str, Any]:
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

    async def chat_stream(self, message: str, image_path: str | None = None) -> AsyncGenerator[dict[str, Any], None]:
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
                    logger.info("Tool call: %s input=%s", tool_name, str(tool_input)[:200])
                    yield {"type": "tool_call", "tool": tool_name, "input": tool_input}

                elif event_kind == "on_tool_end":
                    tool_data = event.get("data", {})
                    tool_output = tool_data.get("output", "")
                    tool_name = event.get("name", "")
                    logger.info(
                        "Tool done: %s output_type=%s output_len=%d",
                        tool_name,
                        type(tool_output).__name__,
                        len(str(tool_output)) if tool_output else 0,
                    )
                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result": str(tool_output) if tool_output else "",
                    }

        except Exception as exc:
            logger.error("Agent stream error: %s", exc, exc_info=True)
            yield {"type": "error", "content": f"处理出错：{exc}"}


detection_agent = DetectionAgent()
