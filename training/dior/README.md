# DIOR 后端部署说明

当前部署包位于 `artifacts/current/deploy/`，由以下文件组成：

- `best.pt`：YOLO11n DIOR 20 类水平框检测权重；
- `metadata.json`：任务类型、版本、输入尺寸和固定类别顺序；
- `metrics.json`：验证集 Precision、Recall、mAP50 和 mAP50-95；
- `SHA256SUMS.txt`：后端启动时使用的权重完整性校验值。

后端默认使用配置：

```dotenv
DIOR_DEPLOY_DIR=../training/dior/artifacts/current/deploy
DIOR_DEVICE=cpu
DIOR_INPUT_SIZE=640
DIOR_CONF_THRESHOLD=0.25
DIOR_IOU_THRESHOLD=0.45
DIOR_VERIFY_SHA256=true
```

使用 GPU 时可在 `src/backend/.env` 中设置 `DIOR_DEVICE=0` 或
`DIOR_DEVICE=cuda:0`。后端启动后可通过以下接口检查和调用模型：

```text
GET  /api/detection/model-info
POST /api/detection/single
POST /api/detection/batch
```

接口需要 Bearer 登录凭证。检测任务会登记为
`dior_facility_detection` 场景，并写入现有的 `DetectionTask`、
`DetectionResult` 和 `ModelVersion` 表；原图与标注图写入 MinIO。

替换新模型时应整体替换部署包，并同步更新版本、指标和 SHA256，不能只覆盖
`best.pt`，否则后端会拒绝类别顺序或校验值不一致的模型。
