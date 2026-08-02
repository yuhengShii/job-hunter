import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

export function useChart(el: Ref<HTMLElement | null>, option: Ref<EChartsOption>) {
  const chart = ref<echarts.ECharts | null>(null)

  onMounted(() => {
    if (!el.value) return
    chart.value = echarts.init(el.value)
    chart.value.setOption(option.value)
  })

  watch(option, (o) => chart.value?.setOption(o, true), { deep: true })

  const onResize = () => chart.value?.resize()
  window.addEventListener('resize', onResize)

  onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    chart.value?.dispose()
  })
}
