"""SQLAlchemy ORM models for the YOLOv11 detection agent platform."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.session import Base


class User(Base):
    """System user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    email = Column(String(100), unique=True, nullable=False, index=True, comment="邮箱")
    hashed_password = Column(String(255), nullable=False, comment="加密密码")
    phone = Column(String(20), nullable=True, comment="手机号")
    avatar = Column(String(500), nullable=True, comment="头像 URL")
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_superuser = Column(Boolean, default=False, comment="是否超级管理员")
    last_login_at = Column(DateTime, nullable=True, comment="最后登录时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    detection_tasks = relationship("DetectionTask", back_populates="user")
    training_tasks = relationship("TrainingTask", back_populates="user")
    chat_sessions = relationship("ChatSession", back_populates="user")
    operation_logs = relationship("OperationLog", back_populates="user")
    semantic_tasks = relationship("SemanticTask", back_populates="user")


class Role(Base):
    """Role definition."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, comment="角色标识")
    display_name = Column(String(100), nullable=False, comment="角色显示名")
    description = Column(String(500), nullable=True, comment="角色描述")
    is_system = Column(Boolean, default=False, comment="是否系统内置角色")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    """Permission definition."""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False, comment="权限编码")
    name = Column(String(100), nullable=False, comment="权限名称")
    module = Column(String(50), nullable=False, comment="所属模块")
    description = Column(String(500), nullable=True, comment="权限描述")

    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class UserRole(Base):
    """User-role association."""

    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base):
    """Role-permission association."""

    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False, index=True)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class DetectionScene(Base):
    """Detection scene configuration."""

    __tablename__ = "detection_scenes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment="场景标识")
    display_name = Column(String(100), nullable=False, comment="场景显示名")
    description = Column(Text, nullable=True, comment="场景描述")
    category = Column(String(50), nullable=False, comment="场景分类")
    class_names = Column(JSON, nullable=False, comment="类别列表")
    class_names_cn = Column(JSON, nullable=True, comment="类别中文名映射")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="创建人")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    detection_tasks = relationship("DetectionTask", back_populates="scene")
    model_versions = relationship("ModelVersion", back_populates="scene")
    training_tasks = relationship("TrainingTask", back_populates="scene")


class DetectionTask(Base):
    """Detection task."""

    __tablename__ = "detection_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="操作用户")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="检测场景")
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), nullable=True, comment="模型版本")
    task_type = Column(String(20), nullable=False, comment="检测类型")
    status = Column(String(20), default="pending", comment="任务状态")
    total_images = Column(Integer, default=0, comment="处理图像总数")
    total_objects = Column(Integer, default=0, comment="检测目标总数")
    total_inference_time = Column(Float, default=0, comment="总推理耗时")
    conf_threshold = Column(Float, default=0.25, comment="置信度阈值")
    iou_threshold = Column(Float, default=0.45, comment="NMS IoU 阈值")
    image_size = Column(Integer, default=640, comment="推理图像尺寸")
    error_message = Column(Text, nullable=True, comment="错误信息")
    analysis_report = Column(Text, nullable=True, comment="分析报告")
    analysis_suggestion = Column(Text, nullable=True, comment="专业建议")
    risk_level = Column(String(20), nullable=True, comment="风险等级")
    analyzed_at = Column(DateTime, nullable=True, comment="分析完成时间")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    user = relationship("User", back_populates="detection_tasks")
    scene = relationship("DetectionScene", back_populates="detection_tasks")
    model_version = relationship("ModelVersion", back_populates="detection_tasks")
    results = relationship("DetectionResult", back_populates="task", cascade="all, delete-orphan")


class DetectionResult(Base):
    """Single object detection result."""

    __tablename__ = "detection_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("detection_tasks.id"), nullable=False, index=True, comment="所属检测任务")
    image_path = Column(String(500), nullable=False, comment="原始图像路径")
    annotated_image_url = Column(String(500), nullable=True, comment="标注图像 URL")
    class_name = Column(String(50), nullable=False, index=True, comment="类别名称")
    class_name_cn = Column(String(50), nullable=True, comment="类别中文名")
    class_id = Column(Integer, nullable=False, comment="类别 ID")
    confidence = Column(Float, nullable=False, comment="置信度")
    bbox = Column(JSON, nullable=False, comment="边界框")
    inference_time = Column(Float, nullable=True, comment="推理耗时")
    image_width = Column(Integer, nullable=True, comment="图像宽度")
    image_height = Column(Integer, nullable=True, comment="图像高度")
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("DetectionTask", back_populates="results")


class TrainingTask(Base):
    """User-owned LoveDA semantic online training task (legacy fields retained)."""

    __tablename__ = "training_tasks"
    __table_args__ = (Index("ix_training_tasks_status_user", "status", "user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="操作用户")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="关联场景")
    task_uuid = Column(String(100), unique=True, nullable=False, index=True, comment="任务唯一标识")
    status = Column(String(20), default="pending", comment="任务状态")
    model_name = Column(String(50), default="yolov11n", comment="基础模型")
    epochs = Column(Integer, default=100, comment="训练轮数")
    img_size = Column(Integer, default=640, comment="图像尺寸")
    batch_size = Column(Integer, default=16, comment="批次大小")
    device = Column(String(20), default="0", comment="训练设备")
    optimizer = Column(String(20), default="SGD", comment="优化器")
    lr0 = Column(Float, default=0.01, comment="初始学习率")
    augment_config = Column(JSON, nullable=True, comment="数据增强配置")
    current_epoch = Column(Integer, default=0, comment="当前轮数")
    progress = Column(Integer, default=0, comment="进度百分比")
    dataset_path = Column(String(500), nullable=True, comment="数据集路径")
    dataset_size = Column(Integer, nullable=True, comment="数据集图像数量")
    data_yaml = Column(String(500), nullable=True, comment="data.yaml 路径")
    error_message = Column(Text, nullable=True, comment="错误信息")
    task_kind = Column(String(32), nullable=False, default="semantic_segmentation")
    runner = Column(String(64), nullable=False, default="loveda_online_worker")
    experiment = Column(String(32), nullable=False, default="S0")
    config_snapshot = Column(JSON, nullable=True)
    requested_model = Column(String(100), nullable=True)
    dataset_key = Column(String(32), nullable=True)
    run_name = Column(String(160), nullable=True, unique=True)
    output_dir = Column(String(500), nullable=True)
    pid = Column(Integer, nullable=True)
    process_group_id = Column(Integer, nullable=True)
    exit_code = Column(Integer, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    stop_requested_at = Column(DateTime, nullable=True)
    last_event_offset = Column(BigInteger, nullable=False, default=0)
    best_epoch = Column(Integer, nullable=True)
    best_miou = Column(Float, nullable=True)
    latest_miou = Column(Float, nullable=True)
    latest_pixel_accuracy = Column(Float, nullable=True)
    artifact_manifest = Column(JSON, nullable=True)
    error_code = Column(String(64), nullable=True)
    cancel_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="开始训练时间")
    completed_at = Column(DateTime, nullable=True, comment="训练完成时间")

    user = relationship("User", back_populates="training_tasks")
    scene = relationship("DetectionScene", back_populates="training_tasks")
    metrics = relationship("TrainingMetric", back_populates="task", cascade="all, delete-orphan")
    model_versions = relationship("ModelVersion", back_populates="training_task")


class TrainingMetric(Base):
    """Per-epoch semantic training metric (legacy detection fields retained)."""

    __tablename__ = "training_metrics"
    __table_args__ = (UniqueConstraint("task_id", "epoch", name="uq_training_metrics_task_epoch"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("training_tasks.id"), nullable=False, index=True, comment="所属训练任务")
    epoch = Column(Integer, nullable=False, comment="当前轮数")
    box_loss = Column(Float, nullable=True, comment="边界框损失")
    cls_loss = Column(Float, nullable=True, comment="分类损失")
    dfl_loss = Column(Float, nullable=True, comment="DFL 损失")
    precision = Column(Float, nullable=True, comment="精确率")
    recall = Column(Float, nullable=True, comment="召回率")
    map50 = Column(Float, nullable=True, comment="mAP@0.50")
    map50_95 = Column(Float, nullable=True, comment="mAP@0.50:0.95")
    train_ce_loss = Column(Float, nullable=True)
    train_dice_loss = Column(Float, nullable=True)
    val_ce_loss = Column(Float, nullable=True)
    val_dice_loss = Column(Float, nullable=True)
    miou = Column(Float, nullable=True)
    pixel_accuracy = Column(Float, nullable=True)
    lr = Column(Float, nullable=True, comment="当前学习率")
    elapsed_seconds = Column(Float, nullable=True)
    raw_metrics = Column(JSON, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("TrainingTask", back_populates="metrics")


class ModelVersion(Base):
    """Model version metadata."""

    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="所属场景")
    training_task_id = Column(Integer, ForeignKey("training_tasks.id"), nullable=True, comment="来源训练任务")
    version = Column(String(50), nullable=False, comment="版本号")
    model_name = Column(String(100), nullable=False, comment="模型名称")
    model_type = Column(String(50), default="yolov11n", comment="模型类型")
    status = Column(String(20), default="active", comment="状态")
    model_path = Column(String(500), nullable=False, comment="本地模型文件路径")
    minio_url = Column(String(500), nullable=True, comment="MinIO 存储 URL")
    map50 = Column(Float, nullable=True, comment="mAP@0.50")
    map50_95 = Column(Float, nullable=True, comment="mAP@0.50:0.95")
    precision = Column(Float, nullable=True, comment="精确率")
    recall = Column(Float, nullable=True, comment="召回率")
    per_class_ap = Column(JSON, nullable=True, comment="各类别 AP")
    description = Column(Text, nullable=True, comment="版本描述")
    file_size = Column(BigInteger, nullable=True, comment="文件大小")
    is_default = Column(Boolean, default=False, comment="是否默认模型")
    task_kind = Column(String(32), nullable=False, default="detection", comment="任务类型")
    runtime = Column(String(32), nullable=True, comment="模型运行时")
    artifact_sha256 = Column(String(64), nullable=True, comment="模型文件 SHA256")
    model_metadata = Column("metadata", JSON, nullable=True, comment="部署元数据快照")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    scene = relationship("DetectionScene", back_populates="model_versions")
    training_task = relationship("TrainingTask", back_populates="model_versions")
    detection_tasks = relationship("DetectionTask", back_populates="model_version")
    semantic_tasks = relationship("SemanticTask", back_populates="model_version")


class SemanticTask(Base):
    """A user-owned asynchronous semantic segmentation task."""

    __tablename__ = "semantic_tasks"
    __table_args__ = (Index("ix_semantic_tasks_user_created", "user_id", "created_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_uuid = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    original_filename = Column(String(255), nullable=False)
    source_object_key = Column(String(500), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    source_content_type = Column(String(100), nullable=False)
    image_width = Column(Integer, nullable=False)
    image_height = Column(Integer, nullable=False)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="semantic_tasks")
    model_version = relationship("ModelVersion", back_populates="semantic_tasks")
    result = relationship("SemanticResult", back_populates="task", uselist=False, cascade="all, delete-orphan")


class SemanticResult(Base):
    """Exactly one set of semantic artifacts and statistics per successful task."""

    __tablename__ = "semantic_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("semantic_tasks.id"), unique=True, nullable=False)
    index_mask_object_key = Column(String(500), nullable=False)
    color_mask_object_key = Column(String(500), nullable=False)
    overlay_object_key = Column(String(500), nullable=False)
    class_statistics = Column(JSON, nullable=False)
    inference_metadata = Column(JSON, nullable=False)
    inference_time_ms = Column(Integer, nullable=False)
    total_time_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    task = relationship("SemanticTask", back_populates="result")


class ChatSession(Base):
    """Agent chat session."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="所属用户")
    session_uuid = Column(String(100), unique=True, nullable=False, index=True, comment="会话唯一标识")
    title = Column(String(200), nullable=True, comment="会话标题")
    status = Column(String(20), default="active", comment="状态")
    message_count = Column(Integer, default=0, comment="消息数量")
    last_message_at = Column(DateTime, nullable=True, comment="最后消息时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """Agent chat message."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True, comment="所属会话")
    role = Column(String(20), nullable=False, comment="消息角色")
    content = Column(Text, nullable=False, comment="消息内容")
    agent_used = Column(String(50), nullable=True, comment="处理 Agent")
    tool_calls = Column(JSON, nullable=True, comment="工具调用记录")
    tool_result = Column(Text, nullable=True, comment="工具调用结果")
    tokens_used = Column(Integer, nullable=True, comment="Token 消耗")
    latency_ms = Column(Integer, nullable=True, comment="响应耗时")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    session = relationship("ChatSession", back_populates="messages")


class OperationLog(Base):
    """Operation audit log."""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="操作用户")
    username = Column(String(50), nullable=True, comment="冗余用户名")
    module = Column(String(50), nullable=False, comment="操作模块")
    action = Column(String(50), nullable=False, comment="操作类型")
    target_type = Column(String(50), nullable=True, comment="操作对象类型")
    target_id = Column(String(100), nullable=True, comment="操作对象 ID")
    description = Column(String(500), nullable=True, comment="操作描述")
    ip_address = Column(String(50), nullable=True, comment="客户端 IP")
    user_agent = Column(String(500), nullable=True, comment="客户端 User-Agent")
    request_method = Column(String(10), nullable=True, comment="HTTP 方法")
    request_path = Column(String(500), nullable=True, comment="请求路径")
    status = Column(String(20), default="success", comment="操作结果")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    user = relationship("User", back_populates="operation_logs")
