# LoveDA → Ultralytics YOLO26 Semantic 工具

本目录与 `backend/frontend` 完全隔离。源目录始终按只读方式打开；所有 mask 转换、报告和可视化都写入独立派生目录。默认行为可重复执行且不覆盖已有派生文件。

## 格式与映射

输出结构：

```text
data/loveda_yolo_semantic/
├─ images/{train,val,test}/{Urban,Rural}/*.png
└─ masks/{train,val}/{Urban,Rural}/*.png
```

图像和 mask 按相同相对路径及 stem 配对。mask 为灰度 `uint8`。源标签映射为：`0→255, 1→0, 2→1, 3→2, 4→3, 5→4, 6→5, 7→6`；输出有效类别是 `0..6`，忽略值是 `255`。YAML 不含 `label_mapping`，因为文件已完成转换。

## 环境

从项目根目录执行以下 Windows `cmd.exe` 命令。路径均使用引号，支持空格和中文：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" -m pip install -r "src\training\loveda_semantic\requirements.txt"
```

## 转换

默认转换 train/val，稳定复制图像且不覆盖已有文件：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\convert_loveda.py"
```

可参数化调用（硬链接失败会自动回退复制；`--overwrite` 仅覆盖派生目录）：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\convert_loveda.py" --source "02 项目资源\数据集\archive" --output "src\training\loveda_semantic\data\loveda_yolo_semantic" --splits train val test --image-mode hardlink
```

## 全量审计

逐文件核验源数据和转换数据的配对、尺寸、图像模式、dtype、标签集合、类别像素数和坏文件，输出 UTF-8 JSON。审计发现问题时退出码为 1：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\audit_loveda.py" --splits train val --report "src\training\loveda_semantic\reports\audit.json"
```

若转换时包含 test，可在审计命令追加 `test`；test 只要求图像，不要求 mask。

## 抽样可视化

每个 split/region 默认固定随机种子抽取 4 个样本，输出原图、彩色 mask、叠加图三联画及图例：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\visualize_samples.py" --count 4 --seed 42
```

## 测试

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" -m unittest discover -s "src\training\loveda_semantic\tests" -v
```

## 训练配置

数据配置位于 `loveda7.yaml`，兼容已确认的 Ultralytics 8.4.89 semantic 数据布局。

### V2 严格单变量短程筛选

入口默认拒绝覆盖已有 run，固定 data/seed=26/AMP/device/workers/deterministic/pretrained/resume 等安全参数；模型可通过 `--model` 在已核实可加载的官方 `yolo26n-sem.pt` 与更大一级 `yolo26s-sem.pt` 间显式选择。S0/S1/S2 锁定各自分辨率和 mosaic，且禁止超过 15 epoch。省略 `--name` 会生成带 UTC 时间的唯一名称。以下命令必须分别执行，不要并行争用 8GB 显存：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\run_semantic_v2.py" train --experiment S0 --batch 2 --epochs 15 --patience 15 --name "v2_s0_e15_i512_b2_m1"
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\run_semantic_v2.py" train --experiment S1 --batch 2 --epochs 15 --patience 15 --name "v2_s1_e15_i640_b2_m1"
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\run_semantic_v2.py" train --experiment S2 --batch 2 --epochs 15 --patience 15 --name "v2_s2_e15_i768_b2_m1"
```

默认 OOM 规则是：只有识别到 CUDA OOM 才以 batch=1 重试一次，所有其他实验参数保持不变，重试写入带 `_oom_retry_b1` 后缀的新目录；原失败目录保留异常、耗时、显存峰值及重试决策。用 `--oom-retry-batch 0` 可禁止自动重试。该规则不会静默更改分辨率、mosaic 或其他实验变量。

完成 S0/S1/S2 并汇总后，将最佳分辨率显式传给 M0（示例假设 640 最佳）：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\run_semantic_v2.py" train --experiment M0 --imgsz 640 --batch 2 --epochs 15 --patience 15 --name "v2_m0_e15_i640_b2_m0"
```

每个 run 的 `experiment_report.json` 记录完整配置、UTC 起止时间、环境、耗时、CUDA 显存峰值、最佳/最终指标和权重路径；启动前的计划快照另存于 `reports/v2_launches/`。短程结果按 best mIoU 降序汇总：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\run_semantic_v2.py" summarize
```

默认输出 `reports/v2_shortlist_summary.csv`。此入口不调用 Day07 全量逐域评估/导出；筛选出候选后，再参数化或复制 Day07 流程对候选 `best.pt` 做 overall/Urban/Rural 完整评估，避免用训练期 mIoU 替代最终 V1 对比口径。

### 1024 + YOLO26s Semantic 三轮冒烟记录

Ultralytics 8.4.89 已实际从官方 assets 下载并成功加载 `yolo26s-sem.pt`，任务类型为 `semantic`、参数量 6,503,142；这确认它是当前 V1 `yolo26n-sem.pt` 的可获取更大一级官方 Semantic 权重。本次严格保持 `imgsz=1024`、`batch=1`、`mosaic=1.0`、AMP、`workers=0`，并禁用 OOM 自动重试，启动命令为：

```bat
"D:\programfile\anaconda\envs\yolo\python.exe" "src\training\loveda_semantic\run_semantic_v2.py" train --experiment custom --model yolo26s-sem.pt --imgsz 1024 --batch 1 --epochs 3 --patience 3 --mosaic 1.0 --oom-retry-batch 0 --name "v2_hr1024_yolo26s_sem_full_e3_b1_m1_20260713T0234Z"
```

训练成功完成 3/3 epoch，运行目录为 `runs/v2_hr1024_yolo26s_sem_full_e3_b1_m1_20260713T0234Z`，总耗时 3288.74 秒（约 54 分 49 秒）。PyTorch 记录的峰值 CUDA allocated/reserved 分别为 1,111,926,272 / 1,142,947,840 bytes（约 1.04 / 1.06 GiB）；第 3 epoch 为当前最佳，mIoU=0.45554、pixel accuracy=0.65255。控制台日志位于 `v2_hr1024_yolo26s_sem_full_e3_b1_m1_20260713T0234Z.console.log`，完整事实记录位于该 run 的 `experiment_report.json`。这些是短程训练期初步指标，不等同于 Day07 最终逐域评估口径；本次未启动 50 epoch 正式训练，也未更改部署或前端。
