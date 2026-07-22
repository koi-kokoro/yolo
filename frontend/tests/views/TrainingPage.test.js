import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const trainingPagePath = resolve(process.cwd(), 'src/views/TrainingPage.vue')
const diorPanelPath = resolve(process.cwd(), 'src/components/training/DiorModelPanel.vue')
const summaryPath = resolve(process.cwd(), 'public/model-dashboard/v2_training_summary.json')

const pageSource = readFileSync(trainingPagePath, 'utf8')
const diorPanelSource = readFileSync(diorPanelPath, 'utf8')
const summary = JSON.parse(readFileSync(summaryPath, 'utf8'))

const asPercent = (value) => `${(value * 100).toFixed(3)}%`

describe('TrainingPage V2 数据口径', () => {
  it('提供 LoveDA 与 DIOR 双模型入口，并按查询参数保存当前选择', () => {
    expect(pageSource).toContain("route.query.model === 'dior'")
    expect(pageSource).toContain("switchModel('loveda')")
    expect(pageSource).toContain("switchModel('dior')")
    expect(pageSource).toContain('<DiorModelPanel v-else ref="diorPanel" />')
  })

  it('DIOR 面板使用目标检测指标与真实单图检测接口，不复用 LoveDA 指标口径', () => {
    expect(diorPanelSource).toContain('getDetectionModelInfo')
    expect(diorPanelSource).toContain('detectSingle')
    expect(diorPanelSource).toContain('验证集 mAP50-95')
    expect(diorPanelSource).toContain('Precision')
    expect(diorPanelSource).toContain('Recall')
    expect(diorPanelSource).toContain('DIOR 20 类目标')
    expect(diorPanelSource).toContain('当前未开放 DIOR 网页在线训练')
    expect(diorPanelSource).not.toContain('metrics.miou')
    expect(diorPanelSource).not.toContain('metrics.pixel_accuracy')
  })

  it('仅加载隔离的 V2 训练与独立评估资产，不加载 baseline 资产', () => {
    expect(pageSource).toContain("fetch('/model-dashboard/v2_training_summary.json')")
    expect(pageSource).toContain("fetch('/model-dashboard/v2_evaluation_metrics.json')")
    expect(pageSource).toContain('/model-dashboard/v2_confusion_matrix_normalized.png')
    expect(pageSource).not.toContain("fetch('/model-dashboard/baseline_report.json')")
    expect(pageSource).not.toContain("fetch('/model-dashboard/metrics.json')")
    expect(pageSource).not.toContain('src="/model-dashboard/confusion_matrix_normalized.png"')
  })

  it('摘要严格反映 V2 experiment_report 与 results.csv 的可证实训练期结果', () => {
    expect(summary.source_type).toBe('training_experiment_report_and_results_csv')
    expect(summary.source_file).toContain(
      'v2_hr1024_yolo26s_sem_full_e50_b4_m1_20260713T0336Z/experiment_report.json',
    )
    expect(summary.model_display_name).toBe('YOLO26s')
    expect(summary.imgsz).toBe(1024)
    expect(summary.batch).toBe(4)
    expect(summary.status).toBe('early_stopped')
    expect(summary.epochs_recorded).toBe(30)
    expect(summary.best_epoch).toBe(20)
    expect(asPercent(summary.best_miou)).toBe('51.476%')
    expect(asPercent(summary.best_pixel_accuracy)).toBe('68.731%')
    expect(asPercent(summary.final_miou)).toBe('50.524%')
  })

  it('明确区分训练期指标，展示完整 V2 曲线与真实完整独立评估', () => {
    expect(pageSource).toContain('训练期最佳验证 mIoU')
    expect(pageSource).toContain('独立完整评估 mIoU')
    expect(pageSource).toContain('完整验证集 · {{ evaluation.images }} 张 · imgsz {{ evaluation.imgsz }}')
    expect(pageSource).toContain('严格来源于 V2 results.csv')
    expect(summary.independent_evaluation.status).toBe('completed')
    expect(summary.independent_evaluation.images).toBe(1669)
    expect(summary.independent_evaluation.imgsz).toBe(1024)
    expect(summary.independent_evaluation.provider).toBe('CPUExecutionProvider')
    expect(asPercent(summary.independent_evaluation.overall_miou)).toBe('51.325%')
    expect(asPercent(summary.independent_evaluation.pixel_accuracy)).toBe('69.037%')
    expect(asPercent(summary.mean_dice_f1)).toBe('67.239%')
    expect(asPercent(summary.domain_metrics.urban_miou)).toBe('56.539%')
    expect(asPercent(summary.domain_metrics.rural_miou)).toBe('43.835%')
    expect(summary.curve.available).toBe(true)
    expect(summary.curve.epochs_recorded).toBe(30)
    expect(summary.curve.metrics).toHaveLength(30)
    expect(summary.curve.metrics.map(({ epoch }) => epoch)).toEqual(
      Array.from({ length: 30 }, (_, index) => index + 1),
    )
    expect(summary.curve.metrics[19]).toMatchObject({
      epoch: 20,
      miou: 0.51476,
      pixel_accuracy: 0.68731,
    })
    expect(summary.curve.metrics[29]).toMatchObject({ epoch: 30, miou: 0.50524 })
    expect(summary.curve_source_sha256).toBe(
      '2d644942838b0796857ff1d0bfb057a95045a4fd128280fcf543ed07d4e99e1d',
    )
  })

  it.each(['50.80%', '54.50%', '43.54%', 'YOLO26n', '512 × 512'])(
    '当前 V2 页面不包含旧 baseline 默认值 %s',
    (legacyValue) => {
      expect(pageSource).not.toContain(legacyValue)
    },
  )
  it('集成在线训练创建、停止、禁用降级与部署版本警告，同时不声称自动部署', () => {
    expect(pageSource).toContain('LoveDA 在线训练任务')
    expect(pageSource).toContain('@click="submitTraining"')
    expect(pageSource).toContain('@click="confirmStopTraining"')
    expect(pageSource).toContain(':disabled="!onlineAvailable"')
    expect(pageSource).toContain('在线训练当前不可用')
    expect(pageSource).toContain('模型登记信息未同步')
    expect(pageSource).toContain('登记信息未同步，不影响当前 V2 推理')
    expect(pageSource).toContain('不会自动替换或部署当前实际推理模型')
    expect(pageSource).toContain('<TrainingMetricsChart :metrics="metrics" />')
  })

  it('保留 V2 静态摘要、完整评估、混淆矩阵、逐类数据和运行时身份口径', () => {
    expect(pageSource).toContain('当前部署模型 / 既有 V2 独立评估')
    expect(pageSource).toContain('实际推理模型')
    expect(pageSource).toContain('runtime / inference metadata')
    expect(pageSource).toContain('V2 训练参数')
    expect(pageSource).toContain('V2 独立完整评估')
    expect(pageSource).toContain('evaluationMetrics?.overall?.per_class')
  })
})
