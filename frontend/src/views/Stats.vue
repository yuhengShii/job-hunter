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
          <el-select v-model="groupBy" style="width: 140px" @change="loadSalary">
            <el-option label="按城市" value="city" />
            <el-option label="按区域" value="district" />
            <el-option label="按地区" value="area" />
          </el-select>
        </div>
      </template>
      <div ref="salaryEl" class="chart" />
    </el-card>

    <el-card class="chart-card">
      <template #header>
        <div class="chart-header">
          <span>职位分布{{ distCity ? `（${distCity}）` : '（按城市）' }}</span>
          <el-select v-model="distCity" placeholder="全部城市" clearable style="width: 160px" @change="loadDistribution">
            <el-option v-for="c in distCityOptions" :key="c" :label="c" :value="c" />
          </el-select>
        </div>
      </template>
      <div ref="distEl" class="chart" />
    </el-card>

    <el-row :gutter="16" class="charts-row">
      <el-col :span="8" v-for="pie in pies" :key="pie.title">
        <el-card class="chart-card">
          <template #header>{{ pie.title }}</template>
          <div :ref="pie.ref" class="chart" />
        </el-card>
      </el-col>
    </el-row>

    <el-card class="chart-card">
      <template #header>时间趋势（近 30 天）</template>
      <div ref="trendEl" class="chart" />
    </el-card>

    <el-card class="chart-card">
      <template #header>标签词频 Top10</template>
      <div ref="tagsEl" class="chart" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { statsApi, type CompanyStats, type SalaryStats, type DistributionResult } from '@/api/stats'
import { useKeywordsStore } from '@/stores/keywords'
import { useChart } from '@/composables/useChart'

const keywordsStore = useKeywordsStore()
const keywordId = ref<number | null>(null)
const groupBy = ref<'city' | 'district' | 'area'>('city')

const overview = ref({ total_jobs: 0, total_cities: 0, total_companies: 0, salary_parsed: 0 })
const salary = ref<SalaryStats | null>(null)
const company = ref<CompanyStats | null>(null)
const trend = ref<{ days: { date: string; count: number }[] } | null>(null)
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
const distCity = ref<string | null>(null)
const distCityOptions = ref<string[]>([])

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

const industryOption = computed<EChartsOption>(() => pieOption(company.value?.industry ?? []))
const typeOption = computed<EChartsOption>(() => pieOption(company.value?.type ?? []))
const sizeOption = computed<EChartsOption>(() => pieOption(company.value?.size ?? []))

function setRef(target: Ref<HTMLElement | null>) {
  return (el: unknown) => {
    target.value = el as HTMLElement | null
  }
}

const pies = [
  { title: '行业分布', ref: setRef(industryEl) },
  { title: '类型分布', ref: setRef(typeEl) },
  { title: '规模分布', ref: setRef(sizeEl) },
]

const trendOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 24, top: 40, bottom: 40 },
  xAxis: { type: 'category', data: (trend.value?.days ?? []).map((d) => d.date) },
  yAxis: { type: 'value' },
  series: [{ type: 'line', smooth: true, areaStyle: {}, data: (trend.value?.days ?? []).map((d) => d.count) }],
}))

const tagsOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 100, right: 24, top: 24, bottom: 40 },
  xAxis: { type: 'value' },
  yAxis: { type: 'category', data: tags.value.map((t) => t.tag).reverse() },
  series: [{ type: 'bar', data: tags.value.map((t) => t.count).reverse() }],
}))

useChart(salaryEl, salaryOption)
useChart(industryEl, industryOption)
useChart(typeEl, typeOption)
useChart(sizeEl, sizeOption)
useChart(trendEl, trendOption)
useChart(tagsEl, tagsOption)

const distOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 90, right: 24, top: 40, bottom: 80 },
  xAxis: { type: 'category', data: (dist.value?.items ?? []).map((i) => i.key), axisLabel: { interval: 0, rotate: 30 } },
  yAxis: { type: 'value', name: '职位数' },
  series: [{ type: 'bar', data: (dist.value?.items ?? []).map((i) => i.count), barMaxWidth: 40 }],
}))
useChart(distEl, distOption)

let statsSeq = 0

async function reload() {
  const seq = ++statsSeq
  const kw = keywordId.value
  const [ov, sa, co, tr, ta, di] = await Promise.all([
    statsApi.overview(kw),
    statsApi.salary(kw, groupBy.value),
    statsApi.company(kw),
    statsApi.trend(kw, 30),
    statsApi.tags(kw, 10),
    statsApi.distribution(kw, distCity.value),
  ])
  if (seq !== statsSeq) return
  overview.value = ov
  salary.value = sa
  company.value = co
  trend.value = tr
  tags.value = ta
  dist.value = di
  if (!distCity.value) {
    distCityOptions.value = (di.items ?? []).map((i) => i.key).filter((k) => k !== '未知')
  }
}

async function loadSalary() {
  const seq = ++statsSeq
  const sa = await statsApi.salary(keywordId.value, groupBy.value)
  if (seq !== statsSeq) return
  salary.value = sa
}

async function loadDistribution() {
  const seq = ++statsSeq
  const di = await statsApi.distribution(keywordId.value, distCity.value)
  if (seq !== statsSeq) return
  dist.value = di
  if (!distCity.value) {
    distCityOptions.value = (di.items ?? []).map((i) => i.key).filter((k) => k !== '未知')
  }
}

onMounted(async () => {
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
.card-num { font-size: 26px; font-weight: 600; text-align: center; }
.card-label { margin-top: 4px; text-align: center; color: var(--el-text-color-secondary); }
</style>
