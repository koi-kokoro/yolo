export function metricValue(value) {
  return value === null || value === undefined || value === '' || !Number.isFinite(Number(value))
    ? null
    : Number(value)
}

export function buildTrainingChartOption(metrics = []) {
  const rows = [...metrics].sort((a, b) => Number(a.epoch) - Number(b.epoch))
  const epochs = rows.map((item) => Number(item.epoch))
  const series = [
    ['训练 CE Loss', 'train_ce_loss', 0],
    ['训练 Dice Loss', 'train_dice_loss', 0],
    ['验证 CE Loss', 'val_ce_loss', 0],
    ['验证 Dice Loss', 'val_dice_loss', 0],
    ['mIoU', 'miou', 1],
    ['Pixel Accuracy', 'pixel_accuracy', 1],
  ].map(([name, key, yAxisIndex]) => ({
    name,
    type: 'line',
    yAxisIndex,
    showSymbol: rows.length < 20,
    connectNulls: false,
    data: rows.map((item) => metricValue(item[key])),
  }))
  return {
    animation: false,
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 58, right: 70, top: 48, bottom: 42 },
    xAxis: { type: 'category', name: 'Epoch', boundaryGap: false, data: epochs },
    yAxis: [
      { type: 'value', name: 'Loss', scale: true },
      {
        type: 'value',
        name: '指标 (%)',
        min: 0,
        max: 1,
        axisLabel: { formatter: (value) => `${Math.round(value * 100)}%` },
      },
    ],
    series,
  }
}
