<template>
  <div>
    <el-card class="filter-card">
      <el-select
        v-model="keywordId"
        placeholder="全部关键字"
        clearable
        style="width: 240px"
        @change="reload"
      >
        <el-option v-for="kw in keywordsStore.list" :key="kw.id" :label="kw.keyword" :value="kw.id" />
      </el-select>
      <el-select v-model="groupBy" style="width: 140px; margin-left: 16px" @change="reload">
        <el-option label="全部" value="all" />
        <el-option label="按城市" value="city" />
        <el-option label="按区域" value="district" />
        <el-option label="按地区" value="area" />
      </el-select>
    </el-card>

    <el-row :gutter="16" class="cards-row">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card>
          <div class="card-num">{{ card.value }}</div>
          <div class="card-label">{{ card.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="chart-card">
      <template #header>
        <div class="chart-header">
          <span>薪资分布（中位薪资）</span>
        </div>
      </template>
      <div ref="salaryEl" class="chart" />
    </el-card>

    <el-card class="chart-card">
      <template #header>
        <div class="chart-header">
          <span>职位分布</span>
        </div>
      </template>
      <div ref="distEl" class="chart" />
    </el-card>

    <el-row :gutter="16" class="charts-row">
      <el-col :span="8" v-for="pie in pies" :key="pie.title">
        <el-card class="chart-card">
          <template #header>
            <div class="chart-header">
              <span>{{ pie.title }}</span>
              <el-button
                v-if="pie.collapsible"
                size="small"
                link
                type="primary"
                @click="industryExpanded = !industryExpanded"
              >
                {{ industryExpanded ? '收起' : `展开全部（${industryItems.length}）` }}
              </el-button>
            </div>
          </template>
          <div :ref="pie.ref" class="chart" />
          <div v-if="pie.collapsible" class="pie-legend">
            <span
              v-for="item in legendIndustries"
              :key="item.key"
              class="pie-legend-item"
              :class="{ 'is-dim': hiddenIndustries.has(item.key) }"
              @click="toggleIndustry(item.key)"
            >
              <i class="pie-legend-swatch" :style="{ background: industryColor(item.key) }" />
              {{ item.key }}（{{ item.count }}）
            </span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="chart-card">
      <template #header>发布时间趋势（近 30 天）</template>
      <div ref="trendEl" class="chart" />
    </el-card>

    <el-card class="chart-card">
      <template #header>标签词频 Top10</template>
      <div ref="tagsEl" class="chart" />
    </el-card>

    <el-dialog v-model="jumpVisible" title="跳转职位列表" width="420px">
      <div class="jump-summary">
        <div>时间：{{ jumpDate }}</div>
        <div v-if="jumpRegion">地区：{{ jumpRegion }}</div>
      </div>
      <el-input v-model="jumpKeyword" placeholder="关键字（留空则不过滤）" clearable style="margin-top: 12px" />
      <template #footer>
        <el-button @click="jumpVisible = false">取消</el-button>
        <el-button type="primary" @click="jumpToJobs">确认跳转</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { statsApi, type CompanyStats, type SalaryStats, type DistributionResult, type TrendResult } from '@/api/stats'
import { useKeywordsStore } from '@/stores/keywords'
import { useChart } from '@/composables/useChart'
import { trendDisplay } from '@/utils/trend'

const router = useRouter()

const keywordsStore = useKeywordsStore()
const keywordId = ref<number | null>(null)
const groupBy = ref<'all' | 'city' | 'district' | 'area'>('all')

const overview = ref({ total_jobs: 0, total_cities: 0, total_companies: 0, salary_parsed: 0 })
const salary = ref<SalaryStats | null>(null)
const company = ref<CompanyStats | null>(null)
const trend = ref<TrendResult | null>(null)
const tags = ref<{ tag: string; count: number }[]>([])
const dist = ref<DistributionResult | null>(null)

const cards = computed(() => [
  { label: '职位总数', value: overview.value.total_jobs },
  { label: '城市数', value: overview.value.total_cities },
  { label: '公司数', value: overview.value.total_companies },
  { label: '薪资可解析', value: overview.value.salary_parsed },
])

const salaryEl = ref<HTMLElement | null>(null)
const industryEl = ref<HTMLElement | null>(null)
const typeEl = ref<HTMLElement | null>(null)
const sizeEl = ref<HTMLElement | null>(null)
const trendEl = ref<HTMLElement | null>(null)
const tagsEl = ref<HTMLElement | null>(null)
const distEl = ref<HTMLElement | null>(null)

const jumpVisible = ref(false)
const jumpDate = ref('')
const jumpRegion = ref('')
const jumpKeyword = ref('')

const salaryOption = computed<EChartsOption>(() => {
  const items = salary.value?.items ?? []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 90, right: 24, top: 40, bottom: 80 },
    xAxis: { type: 'category', data: items.map((i) => i.key), axisLabel: { interval: 0, rotate: 30 } },
    yAxis: { type: 'value', name: '元' },
    series: [{ type: 'bar', data: items.map((i) => i.median), barMaxWidth: 40 }],
  }
})

function pieOption(data: { key: string; count: number }[]): EChartsOption {
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        data: data.map((i) => ({ name: i.key, value: i.count })),
      },
    ],
  }
}

const INDUSTRY_COLORS = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc']

function industryPieOption(data: { key: string; count: number }[]): EChartsOption {
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { show: false, data: data.map((i) => i.key) },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        data: data.map((i) => ({ name: i.key, value: i.count })),
      },
    ],
  }
}

const industryExpanded = ref(false)
const hiddenIndustries = ref<Set<string>>(new Set())
const industryItems = computed(() => company.value?.industry ?? [])
const legendIndustries = computed(() =>
  industryExpanded.value ? industryItems.value : industryItems.value.slice(0, 10),
)
const industryOption = computed<EChartsOption>(() => industryPieOption(industryItems.value))
const typeOption = computed<EChartsOption>(() => pieOption(company.value?.type ?? []))
const sizeOption = computed<EChartsOption>(() => pieOption(company.value?.size ?? []))

function industryColor(name: string): string {
  const idx = industryItems.value.findIndex((i) => i.key === name)
  return INDUSTRY_COLORS[(idx < 0 ? 0 : idx) % INDUSTRY_COLORS.length]
}

function toggleIndustry(name: string) {
  const set = new Set(hiddenIndustries.value)
  if (set.has(name)) {
    set.delete(name)
  } else {
    set.add(name)
  }
  hiddenIndustries.value = set
  industryChart.value?.dispatchAction({ type: 'legendToggleSelect', name })
}

function setRef(target: Ref<HTMLElement | null>) {
  return (el: unknown) => {
    target.value = el as HTMLElement | null
  }
}

const pies = [
  { title: '行业分布', ref: setRef(industryEl), collapsible: true },
  { title: '类型分布', ref: setRef(typeEl), collapsible: false },
  { title: '规模分布', ref: setRef(sizeEl), collapsible: false },
]

const trendOption = computed<EChartsOption>(() => {
  const grouped = trend.value?.series
  if (grouped && grouped.length) {
    const { seriesList, keys, dates } = trendDisplay(grouped)
    const data: [number, number, number][] = []
    seriesList.forEach((s, yi) => {
      s.points.forEach((p, xi) => {
        if (p.count > 0) data.push([xi, yi, p.count])
      })
    })
    const maxVal = Math.max(1, ...seriesList.flatMap((s) => s.points.map((p) => p.count)))
    return {
      tooltip: {
        position: 'top',
        formatter: (params: unknown) => {
          const v = (params as { value: [number, number, number] }).value
          return `${keys[v[1]]}<br/>${dates[v[0]]}：${v[2]} 个`
        },
      },
      grid: { left: 110, right: 16, top: 24, bottom: 70 },
      xAxis: { type: 'category', data: dates },
      yAxis: { type: 'category', data: keys, axisLabel: { fontSize: 11 } },
      visualMap: {
        min: 0,
        max: maxVal,
        calculable: false,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        inRange: { color: ['#ffcdd2', '#ef9a9a', '#e57373', '#f44336', '#c62828'] },
        textStyle: { fontSize: 11 },
      },
      series: [
        {
          type: 'heatmap',
          data,
          emphasis: { itemStyle: { borderColor: '#333', borderWidth: 1 } },
        },
      ],
    }
  }
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: (trend.value?.days ?? []).map((d) => d.date) },
    yAxis: { type: 'value' },
    series: [{ type: 'line', smooth: true, areaStyle: {}, data: (trend.value?.days ?? []).map((d) => d.count) }],
  }
})

const tagsOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 100, right: 24, top: 24, bottom: 40 },
  xAxis: { type: 'value' },
  yAxis: { type: 'category', data: tags.value.map((t) => t.tag).reverse() },
  series: [{ type: 'bar', data: tags.value.map((t) => t.count).reverse() }],
}))

useChart(salaryEl, salaryOption)
const industryChart = useChart(industryEl, industryOption)
useChart(typeEl, typeOption)
useChart(sizeEl, sizeOption)
const trendChart = useChart(trendEl, trendOption)
useChart(tagsEl, tagsOption)

const distOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 90, right: 24, top: 40, bottom: 80 },
  xAxis: { type: 'category', data: (dist.value?.items ?? []).map((i) => i.key), axisLabel: { interval: 0, rotate: 30 } },
  yAxis: { type: 'value', name: '职位数' },
  series: [{ type: 'bar', data: (dist.value?.items ?? []).map((i) => i.count), barMaxWidth: 40 }],
}))
useChart(distEl, distOption)

function jumpToJobs() {
  const query: Record<string, string> = {
    publish_time_from: jumpDate.value,
    publish_time_to: jumpDate.value,
  }
  const gb = groupBy.value
  const skip = !jumpRegion.value || jumpRegion.value === '未知' || jumpRegion.value === '其他'
  if (!skip && gb === 'city') query.city = jumpRegion.value
  else if (!skip && gb === 'district') query.district = jumpRegion.value
  else if (!skip && gb === 'area') query.area = jumpRegion.value
  const kw = jumpKeyword.value.trim()
  if (kw) query.keyword = kw
  jumpVisible.value = false
  router.push({ path: '/jobs', query })
}

let statsSeq = 0

async function reload() {
  const seq = ++statsSeq
  const kw = keywordId.value
  const gb = groupBy.value === 'all' ? 'city' : groupBy.value
  const trendGb = groupBy.value === 'all' ? undefined : groupBy.value
  const [ov, sa, co, tr, ta, di] = await Promise.all([
    statsApi.overview(kw),
    statsApi.salary(kw, gb),
    statsApi.company(kw),
    statsApi.trend(kw, 30, trendGb),
    statsApi.tags(kw, 10),
    statsApi.distribution(kw, gb),
  ])
  if (seq !== statsSeq) return
  overview.value = ov
  salary.value = sa
  company.value = co
  trend.value = tr
  tags.value = ta
  dist.value = di
}

onMounted(async () => {
  trendChart.value?.on('click', (params: unknown) => {
    const p = params as { value?: [number, number, number]; dataIndex?: number; name?: string }
    let date: string | null = null
    let region = ''
    if (trend.value?.series?.length) {
      const v = p.value
      if (!v) return
      const [xi, yi] = v
      const { dates, keys } = trendDisplay(trend.value.series)
      date = dates[xi] ?? null
      region = keys[yi] ?? ''
    } else {
      const days = trend.value?.days ?? []
      const idx = p.dataIndex ?? -1
      date = idx >= 0 ? (days[idx]?.date ?? null) : null
    }
    if (!date) return
    jumpDate.value = date
    jumpRegion.value = region
    jumpKeyword.value = ''
    jumpVisible.value = true
  })
  try {
    await keywordsStore.fetch()
  } catch {
    // 拦截器已提示
  }
  try {
    await reload()
  } catch {
    // 拦截器已提示
  }
})
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.cards-row { margin-bottom: 16px; }
.chart-card { margin-bottom: 16px; }
.chart-header { display: flex; justify-content: space-between; align-items: center; }
.chart { height: 340px; }
.pie-legend {
  margin-top: 8px;
  max-height: 150px;
  overflow-y: auto;
  font-size: 12px;
  line-height: 24px;
}
.pie-legend-item {
  display: inline-flex;
  align-items: center;
  margin-right: 10px;
  cursor: pointer;
  white-space: nowrap;
  color: var(--el-text-color-regular);
}
.pie-legend-item:hover { color: var(--el-color-primary); }
.pie-legend-item.is-dim { opacity: 0.35; text-decoration: line-through; }
.pie-legend-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 4px;
}
.card-num { font-size: 26px; font-weight: 600; text-align: center; }
.card-label { margin-top: 4px; text-align: center; color: var(--el-text-color-secondary); }
.jump-summary { line-height: 24px; color: var(--el-text-color-regular); }
</style>
