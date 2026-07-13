# LoveDA 语义分割训练结果阅读指南

本文档面向第一次接触本项目训练流程的用户，集中说明：V1 已训练结果、训练数据与标签、训练脚本与参数、评估指标、目录关系、可视化查看方法，以及 V2 当前状态。

> 本文所有路径均相对于工作区根目录。当前已经完成并可使用的是 **V1 基线模型**；**V2 尚未训练**。

## 1. 先看结论

- V1 原始训练目录：[`runs/baseline_e50_i512_b2`](runs/baseline_e50_i512_b2/)
- V1 推荐权重：[`runs/baseline_e50_i512_b2/weights/best.pt`](runs/baseline_e50_i512_b2/weights/best.pt)
- V1 最后一次迭代权重：[`runs/baseline_e50_i512_b2/weights/last.pt`](runs/baseline_e50_i512_b2/weights/last.pt)
- V1 完整评估产物：[`artifacts/baseline_e50_i512_b2`](artifacts/baseline_e50_i512_b2/)
- V1 部署包：[`artifacts/baseline_e50_i512_b2/deploy`](artifacts/baseline_e50_i512_b2/deploy/)
- 原始 LoveDA 数据：工作区根目录下的 [`02 项目资源/数据集/archive`](../../../02%20项目资源/数据集/archive/)
- 派生训练数据：[`data/loveda_yolo_semantic`](data/loveda_yolo_semantic/)
- 训练数据配置：[`loveda7.yaml`](loveda7.yaml)
- V1 训练入口：[`run_semantic_baseline.py`](run_semantic_baseline.py)
- 评估、导出和部署打包入口：[`day07_evaluate_export.py`](day07_evaluate_export.py)
- V2 入口已经准备好：[`run_semantic_v2.py`](run_semantic_v2.py)，但目前没有 V2 训练结果。

如只想拿一个模型进行推理，应优先使用部署包中的 [`artifacts/baseline_e50_i512_b2/deploy/best.pt`](artifacts/baseline_e50_i512_b2/deploy/best.pt)。它是从原始训练目录中的 `best.pt` 复制并打包得到的。

## 2. 五类目录必须区分

| 类型 | 路径 | 用途 | 是否为原始资料 |
|---|---|---|---|
| 原始数据 | [`02 项目资源/数据集/archive`](../../../02%20项目资源/数据集/archive/) | LoveDA 原图和原始 mask，转换时按只读源使用 | 是 |
| 派生训练数据 | [`src/training/loveda_semantic/data/loveda_yolo_semantic`](data/loveda_yolo_semantic/) | 将原始数据转换为当前 Ultralytics semantic 可读取的结构 | 否，可由脚本重新生成 |
| 原始训练输出 | [`src/training/loveda_semantic/runs/baseline_e50_i512_b2`](runs/baseline_e50_i512_b2/) | epoch 日志、曲线、批次图片、参数和原始权重 | 否，是训练过程直接产生的结果 |
| 评估产物 | [`src/training/loveda_semantic/artifacts/baseline_e50_i512_b2`](artifacts/baseline_e50_i512_b2/) | 独立完整验证集评估、逐类指标、混淆矩阵和预测样例 | 否，由 Day07 评估脚本生成 |
| 部署包 | [`src/training/loveda_semantic/artifacts/baseline_e50_i512_b2/deploy`](artifacts/baseline_e50_i512_b2/deploy/) | 面向推理和交付整理的权重、ONNX、元数据、指标及校验文件 | 否，由 Day07 打包生成 |

不要把 `runs` 和 `artifacts` 混为一谈：

- `runs` 回答“训练过程产生了什么”。
- `artifacts` 回答“选定最佳权重后，按照统一口径评估出了什么”。
- `deploy` 回答“交付或推理时应携带哪些文件”。

## 3. 原始数据、派生数据和标签在哪里

### 3.1 原始数据

原始 LoveDA 数据位于工作区根目录下的：

```text
02 项目资源/数据集/archive/
```

它是转换脚本的输入源。项目工具不会为了训练而直接改写这里的文件。

### 3.2 派生训练数据

转换后的训练数据位于：

```text
src/training/loveda_semantic/data/loveda_yolo_semantic/
├─ images/
│  ├─ train/
│  │  ├─ Urban/
│  │  └─ Rural/
│  └─ val/
│     ├─ Urban/
│     └─ Rural/
└─ masks/
   ├─ train/
   │  ├─ Urban/
   │  └─ Rural/
   └─ val/
      ├─ Urban/
      └─ Rural/
```

其中：

- `images` 是输入遥感图像。
- `masks` 是语义分割标签，每个像素的数值代表一个类别。
- 图像和 mask 使用相同的相对目录、文件名主体和 `.png` 后缀进行一一配对。
- 标签不是 YOLO 目标检测所使用的 `.txt` 框标注；本任务是语义分割，因此标签是逐像素的 PNG mask。

### 3.3 类别和标签值

[`loveda7.yaml`](loveda7.yaml) 定义了 7 个公开类别：

| 训练标签值 | 类别英文名 | 中文含义 |
|---:|---|---|
| 0 | background | 背景 |
| 1 | building | 建筑 |
| 2 | road | 道路 |
| 3 | water | 水体 |
| 4 | barren | 裸地 |
| 5 | forest | 森林 |
| 6 | agricultural | 农业用地 |
| 255 | ignore | 忽略像素，不参与公开 7 类指标计算 |

原始 mask 的值经过转换后使用以下映射：

```text
原始 0 → 派生 255
原始 1 → 派生 0
原始 2 → 派生 1
原始 3 → 派生 2
原始 4 → 派生 3
原始 5 → 派生 4
原始 6 → 派生 5
原始 7 → 派生 6
```

转换及审计结果记录在 [`reports/audit.json`](reports/audit.json)。当前审计结果为 `ok: true`、`issues: []`。审计确认：

- 训练集 Urban：1156 对图像与 mask。
- 训练集 Rural：1366 对图像与 mask。
- 验证集 Urban：677 对图像与 mask。
- 验证集 Rural：992 对图像与 mask。
- 训练集合计 2522 对。
- 验证集合计 1669 对。
- 未发现缺失配对、额外文件、坏文件或尺寸不一致。

## 4. 预训练不等于自动贴标签

V1 参数中的 `pretrained: true` 表示模型从已有的 `yolo26n-sem.pt` 预训练权重开始优化，而不是完全随机初始化。

这件事**不表示**模型会自动为训练图片生成可靠的训练标签，也不表示可以省略 LoveDA 的人工标注 mask。

本项目实际训练关系是：

```text
预训练模型参数 + 已有训练图像 + 已有人工标注 mask
                    ↓
             在 LoveDA 数据上微调
                    ↓
                V1 权重
```

预训练权重提供的是可继续学习的模型参数；训练监督信号仍来自 [`data/loveda_yolo_semantic/masks`](data/loveda_yolo_semantic/masks/) 中的标签。若未来使用模型预测结果辅助标注，那属于“伪标签/自动标注后人工复核”的另一套流程，不是本次 V1 训练自动发生的事情。

## 5. 使用了哪些脚本

| 脚本 | 作用 | 本次流程中的位置 |
|---|---|---|
| [`convert_loveda.py`](convert_loveda.py) | 复制或硬链接图像，并把原始 mask 映射成训练标签值 | 数据转换 |
| [`audit_loveda.py`](audit_loveda.py) | 检查原始数据和派生数据的配对、尺寸、标签值、像素统计和坏文件 | 数据质量审计 |
| [`visualize_samples.py`](visualize_samples.py) | 抽样输出原图、彩色 mask 和叠加效果 | 训练前标签检查 |
| [`run_semantic_smoke.py`](run_semantic_smoke.py) | 使用小规模数据或短训练验证流程能否跑通 | 冒烟测试，不是正式 V1 |
| [`run_semantic_baseline.py`](run_semantic_baseline.py) | 训练 V1 50-epoch 上限基线，并记录报告 | V1 正式训练入口 |
| [`day07_evaluate_export.py`](day07_evaluate_export.py) | 使用 V1 `best.pt` 做 overall、Urban、Rural 完整评估，导出 ONNX 并组装部署包 | V1 最终评估与交付 |
| [`run_semantic_v2.py`](run_semantic_v2.py) | V2 严格单变量短程筛选与汇总 | 已准备，当前尚未训练 |

## 6. V1 具体怎么训练

### 6.1 准备环境

从工作区根目录执行：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" -m pip install -r "src\training\loveda_semantic\requirements.txt"
```

### 6.2 从原始数据生成派生训练数据

默认转换 `train` 和 `val`：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\convert_loveda.py"
```

显式指定路径的等价形式：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\convert_loveda.py" --source "02 项目资源\数据集\archive" --output "src\training\loveda_semantic\data\loveda_yolo_semantic" --splits train val
```

### 6.3 审计派生数据

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\audit_loveda.py" --splits train val --report "src\training\loveda_semantic\reports\audit.json"
```

### 6.4 查看训练前标签抽样

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\visualize_samples.py" --count 4 --seed 42
```

### 6.5 启动 V1 正式训练

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\run_semantic_baseline.py"
```

脚本固定使用 run 名 `baseline_e50_i512_b2`，并拒绝覆盖已有目录。因此当前 V1 已存在时，不应重复执行该命令，除非先明确制定新的 run 名和保留策略。

### 6.6 使用最佳权重评估并导出

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\day07_evaluate_export.py"
```

该脚本读取 [`runs/baseline_e50_i512_b2/weights/best.pt`](runs/baseline_e50_i512_b2/weights/best.pt)，而不是 `last.pt`，然后生成统一评估结果、逐域可视化、ONNX 和部署包。

> 上述命令用于说明已完成流程如何复现；本文档的创建过程没有启动训练，也没有修改任何训练产物。

## 7. V1 训练参数

训练脚本和 [`runs/baseline_e50_i512_b2/args.yaml`](runs/baseline_e50_i512_b2/args.yaml) 记录的关键参数如下：

| 参数 | V1 值 | 初学者解释 |
|---|---:|---|
| 任务 | semantic | 逐像素语义分割 |
| 初始模型 | `yolo26n-sem.pt` | YOLO26n Semantic 预训练模型 |
| 数据配置 | `src/training/loveda_semantic/loveda7.yaml` | 指向派生数据并声明 7 类 |
| epochs | 50 | 最大训练轮数，不保证一定跑满 |
| 实际记录轮数 | 30 | 因早停而在 30 轮结束 |
| patience | 10 | 连续若干轮无改善后允许提前停止 |
| imgsz | 512 | 训练输入尺寸 512×512 |
| batch | 2 | 每批 2 张图像 |
| device | 0 | 使用第 1 张 CUDA GPU |
| workers | 0 | 数据加载子进程数为 0，适配当前 Windows 环境 |
| amp | true | 使用自动混合精度以降低显存和提高速度 |
| seed | 26 | 固定随机种子 |
| deterministic | true | 尽量使用确定性计算以便复现 |
| pretrained | true | 从预训练参数开始微调 |
| resume | false | 不是从中断点继续训练，而是一次新的训练 |
| optimizer | auto | 由 Ultralytics 自动选择优化器配置 |
| mosaic | 1.0 | 启用 mosaic 数据增强 |
| close_mosaic | 10 | 最后 10 个 epoch 关闭 mosaic |
| plots | true | 保存训练曲线和批次可视化 |
| exist_ok | false | 不允许静默覆盖同名 run |

训练原计划上限是 50 epoch，但实际状态为 `early_stopped`，共记录 30 个 epoch。训练期最佳 epoch 为 20。完整逐 epoch 数据在 [`runs/baseline_e50_i512_b2/results.csv`](runs/baseline_e50_i512_b2/results.csv)，训练总结在 [`runs/baseline_e50_i512_b2/baseline_report.json`](runs/baseline_e50_i512_b2/baseline_report.json)。

## 8. `best.pt` 与 `last.pt` 的区别

### `best.pt`

[`runs/baseline_e50_i512_b2/weights/best.pt`](runs/baseline_e50_i512_b2/weights/best.pt) 是训练期间根据验证指标选出的最佳 checkpoint。本次最佳 epoch 为 20。

适合：

- 正式验证和对比指标。
- 推理演示。
- 导出 ONNX。
- 组装部署包。
- 作为后续候选模型的基准。

### `last.pt`

[`runs/baseline_e50_i512_b2/weights/last.pt`](runs/baseline_e50_i512_b2/weights/last.pt) 是训练停止时最后一个 epoch 的 checkpoint。本次训练在第 30 个 epoch 提前停止，所以它对应训练终点，而不是指标最高点。

适合：

- 排查训练终点状态。
- 在明确兼容的情况下研究续训。
- 分析最佳点之后是否出现退化或过拟合。

### 为什么默认选 `best.pt`

后续完整评估和部署打包都明确读取 `best.pt`。最后一轮只代表时间顺序上的“最后”，不代表验证表现“最好”。因此：

- **推理、评估、导出、交付：优先 `best.pt`。**
- **续训或训练过程诊断：才考虑 `last.pt`。**

部署目录只打包了 `best.pt`，没有把 `last.pt` 当成交付模型。

## 9. V1 关键结果指标

以下数值来自独立完整验证集评估文件 [`artifacts/baseline_e50_i512_b2/metrics.json`](artifacts/baseline_e50_i512_b2/metrics.json)。该评估以 `best.pt` 为输入，并分别统计 overall、Urban 和 Rural。

### 9.1 总体与分域指标

| 范围 | 图像数 | mIoU | Pixel Accuracy | Mean Dice/F1 |
|---|---:|---:|---:|---:|
| overall | 1669 | 0.507951 | 0.691487 | 0.668193 |
| Urban | 677 | 0.545002 | 0.690292 | 0.702066 |
| Rural | 992 | 0.435360 | 0.692285 | 0.587284 |

指标含义：

- **mIoU**：先计算每一类的 Intersection over Union，再对类别求平均；是语义分割最重要的综合指标之一。
- **Pixel Accuracy**：所有有效像素中预测正确的比例；当类别面积不均衡时，不能只看这一项。
- **Mean Dice/F1**：逐类 Dice/F1 的平均值，越接近 1 越好。
- **Precision**：预测成某类的像素中，有多少确实属于该类。
- **Recall**：真实属于某类的像素中，有多少被模型找出来。
- **support_pixels**：该类真实有效像素数量，可帮助判断类别规模是否均衡。

### 9.2 overall 逐类指标

| 类别 | IoU | Dice/F1 | Precision | Recall |
|---|---:|---:|---:|---:|
| background | 0.536301 | 0.698172 | 0.618068 | 0.802131 |
| building | 0.578664 | 0.733106 | 0.700045 | 0.769444 |
| road | 0.539574 | 0.700940 | 0.782834 | 0.634557 |
| water | 0.632248 | 0.774696 | 0.857817 | 0.706261 |
| barren | 0.355409 | 0.524431 | 0.602299 | 0.464392 |
| forest | 0.377638 | 0.548240 | 0.561463 | 0.535626 |
| agricultural | 0.535820 | 0.697764 | 0.814672 | 0.610199 |

从指标可直接看出：

- overall 中 `water` 的 IoU 最高，为 0.632248。
- `barren` 和 `forest` 的 overall IoU 相对较低，是后续优化重点。
- Urban mIoU 高于 Rural mIoU，说明模型在农村域的类别区分更困难。
- Rural 的 `forest` IoU 为 0.176006、`barren` IoU 为 0.226152，是明显短板。

详细逐类、逐域数据还可查看：

- [`artifacts/baseline_e50_i512_b2/metrics_summary.csv`](artifacts/baseline_e50_i512_b2/metrics_summary.csv)
- [`artifacts/baseline_e50_i512_b2/per_class_metrics.csv`](artifacts/baseline_e50_i512_b2/per_class_metrics.csv)
- [`artifacts/baseline_e50_i512_b2/confusion_matrix.csv`](artifacts/baseline_e50_i512_b2/confusion_matrix.csv)

训练期 `results.csv` 中的 mIoU 用于观察 epoch 变化和选择 checkpoint；上表的数值来自 Day07 对整个验证集重新评估后的统一口径。进行最终模型比较时，应优先使用 `artifacts` 中的完整评估指标。

## 10. 如何查看可视化

### 10.1 数据标签抽样可视化

目录：[`reports/samples`](reports/samples/)

其中每张 `*_panel.jpg` 通常展示原图、彩色标签和叠加结果，适合在训练前确认：

- 图像与 mask 是否配对。
- 标签是否错位。
- 类别颜色和空间范围是否合理。
- ignore 区域是否符合预期。

### 10.2 训练过程曲线

- [`runs/baseline_e50_i512_b2/results.png`](runs/baseline_e50_i512_b2/results.png)：训练损失、验证损失、mIoU、像素准确率等随 epoch 的变化。
- [`runs/baseline_e50_i512_b2/results.csv`](runs/baseline_e50_i512_b2/results.csv)：同一信息的表格版本，适合排序或绘图。
- [`runs/baseline_e50_i512_b2/labels.jpg`](runs/baseline_e50_i512_b2/labels.jpg)：训练标签分布相关可视化。

### 10.3 训练批次与验证预测

训练输入示例：

- [`runs/baseline_e50_i512_b2/train_batch0.jpg`](runs/baseline_e50_i512_b2/train_batch0.jpg)
- [`runs/baseline_e50_i512_b2/train_batch1.jpg`](runs/baseline_e50_i512_b2/train_batch1.jpg)
- [`runs/baseline_e50_i512_b2/train_batch2.jpg`](runs/baseline_e50_i512_b2/train_batch2.jpg)

验证标签与预测对照：

- [`runs/baseline_e50_i512_b2/val_batch0_labels.jpg`](runs/baseline_e50_i512_b2/val_batch0_labels.jpg)
- [`runs/baseline_e50_i512_b2/val_batch0_pred.jpg`](runs/baseline_e50_i512_b2/val_batch0_pred.jpg)

同目录还有 `val_batch1_*` 和 `val_batch2_*`。建议成对打开 `labels` 与 `pred`，比较真实标签和模型输出。

### 10.4 混淆矩阵

- [`artifacts/baseline_e50_i512_b2/confusion_matrix.png`](artifacts/baseline_e50_i512_b2/confusion_matrix.png)：overall 像素混淆计数。
- [`artifacts/baseline_e50_i512_b2/confusion_matrix_normalized.png`](artifacts/baseline_e50_i512_b2/confusion_matrix_normalized.png)：按真实类别行归一化，更容易观察某一类被错分到哪里。

看图时，主对角线越明显越好；非对角线上的高值代表两个类别容易互相混淆。

### 10.5 逐类、逐域 IoU

[`artifacts/baseline_e50_i512_b2/per_class_iou_by_domain.png`](artifacts/baseline_e50_i512_b2/per_class_iou_by_domain.png) 同时比较 overall、Urban、Rural 的逐类 IoU，最适合快速发现城乡域差异。

### 10.6 图像、真值、预测三联图

目录：[`artifacts/baseline_e50_i512_b2/sample_predictions`](artifacts/baseline_e50_i512_b2/sample_predictions/)

文件名形如：

```text
Urban_3514_image_gt_pred.png
Rural_2522_image_gt_pred.png
```

每张图从左到右为：

1. 原始遥感图像。
2. Ground Truth 真实标签。
3. Prediction 模型预测。

这是最直观的 V1 定性效果检查方式。

## 11. V1 目录关系

```text
02 项目资源/数据集/archive/                 原始 LoveDA 数据，只读输入
              │
              │ convert_loveda.py
              ▼
src/training/loveda_semantic/data/
└─ loveda_yolo_semantic/                    派生训练数据
   ├─ images/train,val/Urban,Rural
   └─ masks/train,val/Urban,Rural
              │
              │ loveda7.yaml
              │ run_semantic_baseline.py
              ▼
src/training/loveda_semantic/runs/
└─ baseline_e50_i512_b2/                    原始训练输出
   ├─ args.yaml
   ├─ results.csv
   ├─ results.png
   ├─ 训练与验证可视化
   └─ weights/
      ├─ best.pt                            最佳验证 checkpoint
      └─ last.pt                            最后 epoch checkpoint
              │
              │ day07_evaluate_export.py 读取 best.pt
              ▼
src/training/loveda_semantic/artifacts/
└─ baseline_e50_i512_b2/                    完整评估产物
   ├─ metrics.json
   ├─ metrics_summary.csv
   ├─ per_class_metrics.csv
   ├─ confusion_matrix*
   ├─ per_class_iou_by_domain.png
   ├─ sample_predictions/
   └─ deploy/                               部署包
      ├─ best.pt
      ├─ best_dynamic.onnx
      ├─ loveda7.yaml
      ├─ training_args.yaml
      ├─ metrics.json
      ├─ metadata.json
      ├─ export_status.json
      ├─ environment.json
      ├─ INFERENCE.md
      └─ SHA256SUMS.txt
```

## 12. 部署包怎么读

部署包位于 [`artifacts/baseline_e50_i512_b2/deploy`](artifacts/baseline_e50_i512_b2/deploy/)，主要文件含义如下：

| 文件 | 用途 |
|---|---|
| [`deploy/best.pt`](artifacts/baseline_e50_i512_b2/deploy/best.pt) | 推荐的 Ultralytics PyTorch 推理权重 |
| [`deploy/best_dynamic.onnx`](artifacts/baseline_e50_i512_b2/deploy/best_dynamic.onnx) | 导出的动态批次 ONNX 模型 |
| [`deploy/INFERENCE.md`](artifacts/baseline_e50_i512_b2/deploy/INFERENCE.md) | 推理输入输出说明 |
| [`deploy/metadata.json`](artifacts/baseline_e50_i512_b2/deploy/metadata.json) | 类别、颜色、输入尺寸、内部输出注意事项和摘要指标 |
| [`deploy/metrics.json`](artifacts/baseline_e50_i512_b2/deploy/metrics.json) | 随部署包携带的评估指标 |
| [`deploy/training_args.yaml`](artifacts/baseline_e50_i512_b2/deploy/training_args.yaml) | V1 训练参数副本 |
| [`deploy/loveda7.yaml`](artifacts/baseline_e50_i512_b2/deploy/loveda7.yaml) | 数据类别配置副本 |
| [`deploy/export_status.json`](artifacts/baseline_e50_i512_b2/deploy/export_status.json) | ONNX 导出及运行时验证状态 |
| [`deploy/environment.json`](artifacts/baseline_e50_i512_b2/deploy/environment.json) | Python、CUDA 和关键依赖版本 |
| [`deploy/SHA256SUMS.txt`](artifacts/baseline_e50_i512_b2/deploy/SHA256SUMS.txt) | 文件完整性校验值 |

若直接使用 ONNX，必须先阅读 `export_status.json` 和 `INFERENCE.md`，确认输入预处理、输出语义及运行时验证状态；不要仅凭文件存在就假定所有推理代码都与其输出格式兼容。

## 13. V2 当前尚未训练

V2 的实验入口和短程筛选方案已经写入 [`run_semantic_v2.py`](run_semantic_v2.py)，预设包括：

| 实验 | imgsz | mosaic | 目的 |
|---|---:|---:|---|
| S0 | 512 | 1.0 | V1 分辨率短程基准 |
| S1 | 640 | 1.0 | 单变量提高分辨率 |
| S2 | 768 | 1.0 | 继续单变量提高分辨率 |
| M0 | 由最佳 S 组决定 | 0.0 | 在最佳分辨率下单变量关闭 mosaic |

但是当前工作区中：

- [`reports/v2_shortlist_summary.csv`](reports/v2_shortlist_summary.csv) 只有表头，没有任何实验记录。
- 当前没有可确认的 `v2_*` 完成训练目录或 V2 `experiment_report.json` 结果。
- 因此不能声称 V2 已训练，不能给出 V2 最佳模型，也不能把 V2 与 V1 做指标优劣结论。
- 现阶段所有正式模型、指标、可视化和部署结论均属于 **V1 `baseline_e50_i512_b2`**。

未来只有在 S0、S1、S2、M0 实际运行完成，并对候选 `best.pt` 执行与 V1 一致的 overall、Urban、Rural 完整评估后，才可以进行公平比较。训练期短程 mIoU 不能直接替代 Day07 完整评估口径。

## 14. 初学者推荐阅读顺序

1. 打开 [`reports/samples`](reports/samples/) 确认数据和标签长什么样。
2. 打开 [`runs/baseline_e50_i512_b2/results.png`](runs/baseline_e50_i512_b2/results.png) 查看训练过程。
3. 成对查看 `val_batch*_labels.jpg` 和 `val_batch*_pred.jpg`。
4. 打开 [`artifacts/baseline_e50_i512_b2/sample_predictions`](artifacts/baseline_e50_i512_b2/sample_predictions/) 查看原图、真值、预测三联图。
5. 查看 [`artifacts/baseline_e50_i512_b2/per_class_iou_by_domain.png`](artifacts/baseline_e50_i512_b2/per_class_iou_by_domain.png) 理解 Urban 与 Rural 差异。
6. 查看 [`artifacts/baseline_e50_i512_b2/metrics.json`](artifacts/baseline_e50_i512_b2/metrics.json) 和 CSV 文件读取精确数值。
7. 推理或交付时使用 [`artifacts/baseline_e50_i512_b2/deploy`](artifacts/baseline_e50_i512_b2/deploy/) 中的文件，默认优先 `best.pt`。
8. 明确记录当前状态：V1 已完成，V2 尚未训练。
