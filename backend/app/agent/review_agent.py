"""对结构化分析结论进行证据引用与措辞边界核验。"""

from __future__ import annotations

import re
from typing import Any, AsyncGenerator


class ReviewAgent:
    """确定性审查优先；当前不依赖第二个 LLM 充当“裁判”。"""

    _ALLOWED_CLAIM_TYPES = {"observation", "recommendation"}
    _OVERCLAIM_WORDS = ("确定属于", "必然是", "已经证明", "绝对", "百分之百")

    @staticmethod
    def _resolve(evidence: dict[str, Any], reference: str) -> tuple[bool, Any]:
        """解析受限的 dotted/list-index 证据路径，不执行任意表达式。"""
        current: Any = evidence
        for key, index_text in re.findall(r"([A-Za-z0-9_-]+)|\[(\d+)\]", reference):
            if key:
                if not isinstance(current, dict) or key not in current:
                    return False, None
                current = current[key]
            else:
                index = int(index_text)
                if not isinstance(current, list) or index >= len(current):
                    return False, None
                current = current[index]
        return bool(reference), current

    @classmethod
    def review(cls, workflow_state: dict[str, Any] | None) -> dict[str, Any]:
        evidence = (workflow_state or {}).get("evidence_pack") or {}
        analysis = evidence.get("analysis") or {}
        claims = analysis.get("claims") if isinstance(analysis, dict) else None
        issues: list[dict[str, str]] = []

        if not claims:
            issues.append(
                {
                    "code": "missing_claims",
                    "message": "分析结果没有可核验的结构化结论。",
                }
            )
        else:
            for index, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    issues.append(
                        {
                            "code": "invalid_claim",
                            "message": f"第 {index + 1} 条结论格式无效。",
                        }
                    )
                    continue
                text = str(claim.get("text") or "").strip()
                claim_type = str(claim.get("claim_type") or "")
                evidence_ref = str(claim.get("evidence_ref") or "").strip()
                if not text or claim_type not in cls._ALLOWED_CLAIM_TYPES:
                    issues.append(
                        {
                            "code": "invalid_claim",
                            "message": f"第 {index + 1} 条结论缺少文本或合法类型。",
                        }
                    )
                if claim_type == "observation" and (
                    not evidence_ref or claim.get("observed_value") is None
                ):
                    issues.append(
                        {
                            "code": "missing_evidence",
                            "message": f"第 {index + 1} 条观察结论缺少证据引用或观测值。",
                        }
                    )
                elif claim_type == "observation":
                    found, source_value = cls._resolve(evidence, evidence_ref)
                    if not found:
                        issues.append(
                            {
                                "code": "invalid_evidence_ref",
                                "message": f"第 {index + 1} 条观察结论引用了不存在的证据。",
                            }
                        )
                    elif source_value != claim.get("observed_value"):
                        issues.append(
                            {
                                "code": "evidence_mismatch",
                                "message": f"第 {index + 1} 条观察值与原始证据不一致。",
                            }
                        )
                if any(word in text for word in cls._OVERCLAIM_WORDS):
                    issues.append(
                        {
                            "code": "overclaim",
                            "message": f"第 {index + 1} 条结论使用了超出证据边界的确定性措辞。",
                        }
                    )

        return {
            "passed": not issues,
            "issues": issues,
            "checked_claims": len(claims or []),
            "review_mode": "deterministic",
        }

    async def chat_stream(
        self,
        workflow_state: dict[str, Any] | None = None,
        **_: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        result = self.review(workflow_state)
        yield {"type": "review_result", "result": result}


review_agent = ReviewAgent()
