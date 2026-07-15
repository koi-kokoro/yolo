"""Pydantic request and response schemas used by the API layer."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    """User registration request."""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLogin(BaseModel):
    """User login request."""

    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserBrief(BaseModel):
    """Brief user info embedded in token responses."""

    id: int
    username: str
    email: str
    avatar: Optional[str] = None
    roles: list[str] = []

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """JWT login response."""

    access_token: str
    token_type: str = "bearer"
    user: UserBrief


class UserResponse(BaseModel):
    """User detail response without sensitive fields."""

    id: int
    username: str
    email: str
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool
    is_superuser: bool
    roles: list[str] = []
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """User profile update request."""

    phone: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None


class ChangePassword(BaseModel):
    """Password change request."""

    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class RoleResponse(BaseModel):
    """Role response."""

    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    is_system: bool
    permissions: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    """Role creation request."""

    name: str = Field(..., min_length=2, max_length=50, description="角色标识")
    display_name: str = Field(..., description="角色显示名")
    description: Optional[str] = None
    permission_codes: list[str] = Field(default=[], description="权限编码列表")


class PermissionResponse(BaseModel):
    """Permission response."""

    id: int
    code: str
    name: str
    module: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ModelVersionBrief(BaseModel):
    """Brief model version response."""

    id: int
    version: str
    model_name: str
    model_type: str
    map50: Optional[float] = None
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SceneCreate(BaseModel):
    """Detection scene creation request."""

    name: str = Field(..., description="场景标识，如 remote_sensing")
    display_name: str = Field(..., description="场景显示名，如 遥感目标检测")
    description: Optional[str] = None
    category: str = Field(..., description="分类")
    class_names: list[str] = Field(..., description="类别列表")
    class_names_cn: Optional[dict[str, str]] = Field(None, description="中文名映射")


class SceneResponse(BaseModel):
    """Detection scene response."""

    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    category: str
    class_names: list
    class_names_cn: Optional[dict] = None
    is_active: bool
    default_model: Optional[ModelVersionBrief] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DetectionTaskResponse(BaseModel):
    """Detection task response."""

    id: int
    user_id: int
    scene_id: int
    scene_name: Optional[str] = None
    model_version_id: Optional[int] = None
    task_type: str
    status: str
    total_images: int
    total_objects: int
    total_inference_time: float
    conf_threshold: float
    iou_threshold: float
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DetectionResultResponse(BaseModel):
    """Single detection result response."""

    id: int
    task_id: int
    image_path: str
    annotated_image_url: Optional[str] = None
    class_name: str
    class_name_cn: Optional[str] = None
    class_id: int
    confidence: float
    bbox: list
    inference_time: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DetectionTaskDetail(BaseModel):
    """Detection task detail with results."""

    task: DetectionTaskResponse
    results: list[DetectionResultResponse] = []


class DetectionStatistics(BaseModel):
    """Detection statistics response."""

    total_tasks: int
    total_images: int
    total_objects: int
    avg_inference_time: float
    class_distribution: dict[str, int]
    daily_trend: list[dict]
    scene_distribution: dict[str, int]


class TrainingTaskCreate(BaseModel):
    """LoveDA semantic online training request; clients select keys, never paths."""

    model: str = Field(default="yolo26n-sem.pt", max_length=100)
    dataset_key: str = Field(default="full", pattern="^(full|smoke)$")
    experiment: str = Field(default="S0", pattern="^(S0|S1|S2|M0|custom)$")
    device: str = Field(default="0", max_length=20)
    epochs: Optional[int] = Field(default=None, ge=1)
    batch_size: int = Field(default=4, ge=1, le=4)
    img_size: Optional[int] = Field(default=None, ge=128, le=2048)
    patience: int = Field(default=15, ge=1, le=100)
    mosaic: Optional[float] = Field(default=None, ge=0, le=1)


class TrainingTaskResponse(BaseModel):
    """Sanitized online training task response."""

    id: int
    task_uuid: str
    status: str
    task_kind: str
    runner: str
    experiment: str
    requested_model: Optional[str] = None
    dataset_key: Optional[str] = None
    run_name: Optional[str] = None
    epochs: int
    current_epoch: int
    progress: int
    batch_size: int
    img_size: int
    device: str
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    heartbeat_at: Optional[datetime] = None
    stop_requested_at: Optional[datetime] = None
    best_epoch: Optional[int] = None
    best_miou: Optional[float] = None
    latest_miou: Optional[float] = None
    latest_pixel_accuracy: Optional[float] = None
    artifact_manifest: Optional[list | dict] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    cancel_reason: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TrainingMetricResponse(BaseModel):
    """Per-epoch LoveDA segmentation metric response."""

    epoch: int
    train_ce_loss: Optional[float] = None
    train_dice_loss: Optional[float] = None
    val_ce_loss: Optional[float] = None
    val_dice_loss: Optional[float] = None
    miou: Optional[float] = None
    pixel_accuracy: Optional[float] = None
    lr: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    raw_metrics: Optional[dict] = None
    recorded_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ModelVersionResponse(BaseModel):
    """Model version detail response."""

    id: int
    scene_id: int
    scene_name: Optional[str] = None
    training_task_id: Optional[int] = None
    version: str
    model_name: str
    model_type: str
    status: str
    model_path: str
    minio_url: Optional[str] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    per_class_ap: Optional[dict] = None
    description: Optional[str] = None
    file_size: Optional[int] = None
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelVersionCreate(BaseModel):
    """Manual model version creation request."""

    scene_id: int
    version: str = Field(..., description="版本号")
    model_name: str = Field(..., description="模型名称")
    model_type: str = Field(default="yolov11n", description="模型类型")
    description: Optional[str] = None


class ChatSessionCreate(BaseModel):
    """Chat session creation request."""

    title: Optional[str] = None


class ChatSessionResponse(BaseModel):
    """Chat session response."""

    id: int
    session_uuid: str
    title: Optional[str] = None
    status: str
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageRequest(BaseModel):
    """Chat message request."""

    session_id: Optional[int] = Field(None, description="会话 ID")
    content: str = Field(..., min_length=1, max_length=5000, description="消息内容")


class ChatMessageResponse(BaseModel):
    """Chat message response."""

    id: int
    session_id: int
    role: str
    content: str
    agent_used: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_result: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    """Chat history response."""

    session: ChatSessionResponse
    messages: list[ChatMessageResponse] = []


class OperationLogResponse(BaseModel):
    """Operation log response."""

    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    module: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SemanticEvaluateRequest(BaseModel):
    """Semantic model evaluation request."""

    device: str = Field(default="cpu", description="评估设备: cpu / 0")
    force: bool = Field(default=False, description="是否强制重新运行评估")


class SemanticEvaluateResponse(BaseModel):
    """Semantic model evaluation response."""

    source: str = Field(..., description="指标来源: cached / evaluated")
    report: dict
    elapsed_seconds: Optional[float] = None
    warning: Optional[str] = None


class SemanticExportRequest(BaseModel):
    """Semantic model export request."""

    version: Optional[str] = Field(None, description="版本号，不传则自动生成")
    description: Optional[str] = Field(None, description="版本描述")
    set_default: bool = Field(default=False, description="是否设为默认模型")
    upload_minio: bool = Field(default=True, description="是否上传到 MinIO")


class SemanticExportResponse(BaseModel):
    """Semantic model export response."""

    model_version_id: int
    version: str
    scene_id: int
    model_name: str
    model_path: str
    export_dir: str
    minio_url: Optional[str] = None
    file_size: Optional[int] = None
    is_default: bool
    evaluation: dict
    message: str


class SemanticPredictResponse(BaseModel):
    """Semantic ad-hoc prediction response."""

    total_objects: Optional[int] = None
    class_statistics: list[dict]
    annotated_image: str
    inference_time_ms: Optional[float] = None
    model: Optional[str] = None


class ChatStreamRequest(BaseModel):
    """Chat stream request."""

    message: str = Field(..., min_length=1, max_length=5000, description="用户消息")
    image_path: Optional[str] = Field(None, description="已上传图片的服务端路径")
    session_id: Optional[int] = Field(None, description="会话 ID")
    scene_id: Optional[int] = Field(None, description="检测场景 ID（可选，未提供时使用默认场景）")


class ChatStreamEvent(BaseModel):
    """A single SSE event payload from the chat stream."""

    type: str = Field(..., description="事件类型: text_chunk / tool_call / tool_result / error")
    content: Optional[str] = None
    tool: Optional[str] = None
    input: Optional[dict] = None
    result: Optional[str] = None


class SegmentationSingleResponse(BaseModel):
    """Single-image segmentation shortcut response."""

    mode: str
    filename: str
    image_width: int
    image_height: int
    annotated_image: Optional[str] = None
    class_statistics: list[dict]
    class_counts: dict[str, int]
    inference_time_ms: Optional[float] = None
    model: Optional[str] = None


class SegmentationBatchResponse(BaseModel):
    """Batch / ZIP segmentation shortcut response."""

    mode: str
    total_images: int
    successful_images: int
    total_inference_ms: float
    class_counts: dict[str, int]
    annotated_images: list[dict]
    zip_filename: Optional[str] = None


class ChatUploadResponse(BaseModel):
    """Chat image upload response."""

    image_path: str = Field(..., description="上传图片在服务器上的临时路径")


class ApiResponse(BaseModel):
    """Unified API response wrapper."""

    code: int = 200
    message: str = "success"
    data: Optional[dict | list] = None


class PageParams(BaseModel):
    """Pagination query params."""

    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class PageResponse(BaseModel):
    """Pagination response."""

    total: int
    page: int
    page_size: int
    total_pages: int
    items: list


class SemanticModelBrief(BaseModel):
    id: Optional[int] = None
    version: str
    model_name: str


class SemanticClassStatistic(BaseModel):
    class_id: int
    name: str
    display_name: str
    rgb: list[int]
    pixel_count: int
    ratio: float


class SemanticResultResponse(BaseModel):
    index_mask_url: str
    color_mask_url: str
    overlay_url: str
    class_statistics: list[SemanticClassStatistic]
    inference_time_ms: int
    total_time_ms: int
    inference_metadata: dict


class SemanticTaskCreateResponse(BaseModel):
    id: int
    task_uuid: str
    status: str
    model_version: SemanticModelBrief
    original_filename: str
    created_at: datetime


class SemanticTaskSummary(BaseModel):
    task_uuid: str
    status: str
    original_filename: str
    model_version: SemanticModelBrief
    image_width: int
    image_height: int
    inference_time_ms: Optional[int] = None
    total_time_ms: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SemanticTaskPage(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[SemanticTaskSummary]


class SemanticTaskError(BaseModel):
    code: str
    message: str


class SemanticTaskDetail(BaseModel):
    task_uuid: str
    status: str
    original_filename: str
    source_url: Optional[str] = None
    model_version: SemanticModelBrief
    result: Optional[SemanticResultResponse] = None
    error: Optional[SemanticTaskError] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class SemanticModelInfo(BaseModel):
    ready: bool
    engine: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_sha256: Optional[str] = None
    input_size: Optional[list[int]] = None
    classes: list[dict] = []
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    app_name: str
    version: str
    database: Optional[str] = None
    redis: Optional[str] = None
    minio: Optional[str] = None
