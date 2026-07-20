<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { buildTrainingChartOption } from './trainingChartOptions'

use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  metrics: { type: Array, default: () => [] },
})

const chartRoot = ref(null)
let chart = null
let resizeObserver = null

const hasMetrics = computed(() => props.metrics.length > 0)

async function renderChart() {
  await nextTick()
  if (!hasMetrics.value || !chartRoot.value) {
    chart?.clear()
    return
  }
  if (!chart) chart = init(chartRoot.value)
  chart.setOption(buildTrainingChartOption(props.metrics), true)
}

watch(() => props.metrics, renderChart, { deep: true })

onMounted(() => {
  renderChart()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    if (chartRoot.value) resizeObserver.observe(chartRoot.value)
  } else {
    window.addEventListener('resize', renderResize)
  }
})

function renderResize() {
  chart?.resize()
}

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', renderResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="training-chart-shell">
    <div v-show="hasMetrics" ref="chartRoot" class="training-chart" aria-label="在线训练指标曲线"></div>
    <el-empty v-if="!hasMetrics" description="暂无 epoch 指标，训练开始后将增量显示 Loss、mIoU 与 Pixel Accuracy" />
  </div>
</template>

<style scoped lang="scss">
.training-chart-shell {
  min-height: 360px;
  padding: 8px;
  background:
    linear-gradient(rgba(78, 103, 138, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(78, 103, 138, 0.035) 1px, transparent 1px),
    rgba(248, 250, 253, 0.7);
  background-size: 32px 32px, 32px 32px, auto;
  border: 1px solid rgba(78, 103, 138, 0.1);
  border-radius: 12px;
}

.training-chart {
  width: 100%;
  height: 360px;
}
</style>
