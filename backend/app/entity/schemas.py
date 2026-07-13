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
    """Training task creation request."""

    scene_id: int = Field(..., description="关联场景 ID")
    model_name: str = Field(default="yolov11n", description="基础模型")
    epochs: int = Field(default=100, ge=10, le=500, description="训练轮数")
    img_size: int = Field(default=640, description="图像尺寸")
    batch_size: int = Field(default=16, ge=1, le=64, description="批次大小")
    device: str = Field(default="0", description="训练设备")
    optimizer: str = Field(default="SGD", description="优化器")
    lr0: float = Field(default=0.01, description="初始学习率")
    augment_config: Optional[dict] = Field(None, description="数据增强配置")


class TrainingTaskResponse(BaseModel):
    """Training task response."""

    id: int
    user_id: int
    scene_id: int
    scene_name: Optional[str] = None
    task_uuid: str
    status: str
    model_name: str
    epochs: int
    current_epoch: int
    progress: int
    img_size: int
    batch_size: int
    device: str
    dataset_size: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TrainingMetricResponse(BaseModel):
    """Per-epoch training metric response."""

    epoch: int
    box_loss: Optional[float] = None
    cls_loss: Optional[float] = None
    dfl_loss: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    lr: Optional[float] = None

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
