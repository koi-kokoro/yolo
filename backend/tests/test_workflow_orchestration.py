"""不依赖外部模型服务的任务计划、共享证据与审核单元测试。"""

from __future__ import annotations

from app.agent.review_agent import ReviewAgent
from app.orchestration.supervisor import Supervisor
from app.orchestration.workflow import (
    AgentStep,
    TaskPlan,
    WorkflowState,
    build_land_cover_analysis,
    compact_evidence,
)


def test_single_intent_plan_keeps_existing_route():
    plan = Supervisor().plan("什么是 IoU")
    assert plan.is_workflow is False
    assert [step.agent for step in plan.steps] == ["qa"]


def test_image_report_builds_evidence_review_pipeline():
    plan = Supervisor().plan("分析这张图片并生成巡查报告", "trusted.png")
    assert plan.primary_route == "report"
    assert [step.agent for step in plan.steps] == [
        "detection",
        "analysis",
        "review",
        "report",
    ]
    assert plan.steps[-1].depends_on == ("review",)


def test_evaluation_export_is_a_two_step_plan():
    plan = Supervisor().plan("查看当前模型评估结果并导出 CSV")
    assert [step.agent for step in plan.steps] == ["evaluation", "export"]


def test_shared_evidence_removes_binary_paths_and_limits_lists():
    compact = compact_evidence(
        {
            "annotated_image": "base64-data",
            "image_path": "C:/private/image.png",
            "model_path": "C:/private/model.pt",
            "class_statistics": [{"name": "water"}] * 120,
        }
    )
    assert "annotated_image" not in compact
    assert "image_path" not in compact
    assert "model_path" not in compact
    assert len(compact["class_statistics"]) == 100


def test_workflow_state_records_structured_tool_and_analysis_results():
    step = AgentStep("analysis", "analysis")
    state = WorkflowState(TaskPlan("analysis", (step,), "test"))
    state.record_event(
        step,
        {"type": "tool_result", "result": '{"total_tasks": 2}'},
    )
    state.record_event(
        step,
        {
            "type": "analysis_result",
            "result": {
                "claims": [
                    {
                        "text": "共有 2 次任务。",
                        "claim_type": "observation",
                        "evidence_ref": "tool_results.analysis.total_tasks",
                        "observed_value": 2,
                    }
                ]
            },
        },
    )
    assert state.evidence_pack["tool_results"]["analysis"]["total_tasks"] == 2
    assert state.evidence_pack["analysis"]["claims"][0]["observed_value"] == 2


def test_review_rejects_missing_evidence_and_overclaim():
    result = ReviewAgent.review(
        {
            "evidence_pack": {
                "analysis": {
                    "claims": [
                        {
                            "text": "这里绝对是工业区。",
                            "claim_type": "observation",
                            "evidence_ref": "",
                            "observed_value": None,
                        }
                    ]
                }
            }
        }
    )
    assert result["passed"] is False
    assert {issue["code"] for issue in result["issues"]} == {
        "missing_evidence",
        "overclaim",
    }


def test_review_accepts_grounded_observation():
    result = ReviewAgent.review(
        {
            "evidence_pack": {
                "tool_results": {
                    "detection": {
                        "class_statistics": [{"name": "water", "ratio": 0.2}]
                    }
                },
                "analysis": {
                    "claims": [
                        {
                            "text": "水体像素占比为 20.00%。",
                            "claim_type": "observation",
                            "evidence_ref": "tool_results.detection.class_statistics[0].ratio",
                            "observed_value": 0.2,
                        }
                    ]
                }
            }
        }
    )
    assert result == {
        "passed": True,
        "issues": [],
        "checked_claims": 1,
        "review_mode": "deterministic",
    }


def test_sorted_image_analysis_keeps_original_evidence_indexes():
    """类别按占比重排后，证据引用仍必须指向原始 class_statistics。"""
    class_statistics = [
        {"name": "building", "display_name": "建筑", "pixel_count": 10, "ratio": 0.1},
        {"name": "farmland", "display_name": "农田", "pixel_count": 60, "ratio": 0.6},
        {"name": "road", "display_name": "道路", "pixel_count": 30, "ratio": 0.3},
    ]
    detection = {"class_statistics": class_statistics}
    analysis = build_land_cover_analysis(detection)
    assert analysis["claims"][0]["evidence_ref"] == (
        "tool_results.detection.class_statistics[1].ratio"
    )

    reviewed_state = {
        "evidence_pack": {
            "tool_results": {"detection": detection},
            "analysis": analysis,
        }
    }
    assert ReviewAgent.review(reviewed_state)["passed"] is True
