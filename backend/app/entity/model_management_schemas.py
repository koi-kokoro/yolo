"""Read-only model management response schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ArtifactInfo(BaseModel):
    """Safe file metadata; paths are intentionally excluded."""

    name: str
    exists: bool
    size_bytes: int | None = None
    modified_at: datetime | None = None
    declared_sha256: str | None = None


class TrainingCurvePoint(BaseModel):
    epoch: int
    miou: float | None = None
    pixel_accuracy: float | None = None
    train_ce_loss: float | None = None
    train_dice_loss: float | None = None
    val_ce_loss: float | None = None
    val_dice_loss: float | None = None


class ModelManagementModel(BaseModel):
    id: str
    display_name: str
    source_type: Literal["deployed_artifact", "training_run"]
    lifecycle_status: str
    deployment_status: Literal["deployed", "not_deployed"]
    stale: bool = False
    epoch_target: int | None = None
    epochs_recorded: int = 0
    current_epoch: int | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    latest_miou: float | None = None
    best_miou: float | None = None
    pixel_accuracy: float | None = None
    training_parameters: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    training_curve: list[TrainingCurvePoint] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    export_status: dict[str, Any] | None = None
    report: dict[str, Any] | None = None


class ModelManagementList(BaseModel):
    total: int
    items: list[ModelManagementModel]


class ModelManagementOverview(BaseModel):
    total: int
    deployed: int
    training: int
    finalizing: int
    stale: int
    models: list[ModelManagementModel]
