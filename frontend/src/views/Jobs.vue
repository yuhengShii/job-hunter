<template>
  <div>
    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="关键字">
          <el-input v-model="query.keyword" clearable placeholder="职位/地区包含" style="width: 180px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="城市">
          <el-select v-model="query.city" clearable placeholder="全部" style="width: 140px" @change="onCityChange">
            <el-option v-for="c in cityOptions" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="区域">
          <el-select v-model="query.district" clearable placeholder="全部" style="width: 140px" :disabled="districtOptions.length === 0" @change="search">
            <el-option v-for="d in districtOptions" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="公司">
          <el-input v-model="query.company_id" clearable placeholder="公司 ID" style="width: 160px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="query.tag" clearable style="width: 140px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="薪资区间">
          <el-input-number v-model="query.salary_min" :min="0" :step="1000" placeholder="最低" @change="search" />
          <span class="sep">~</span>
          <el-input-number v-model="query.salary_max" :min="0" :step="1000" placeholder="最高" @change="search" />
        </el-form-item>
        <el-form-item label="排序">
          <el-select v-model="query.primary_sort" style="width: 130px" @change="search">
            <el-option label="默认" value="" />
            <el-option label="活跃值" value="activity_score" />
            <el-option label="发布时间" value="publish_time" />
          </el-select>
          <el-select v-model="query.primary_dir" style="width: 90px" :disabled="!query.primary_sort" @change="search">
            <el-option label="降序" value="desc" />
            <el-option label="升序" value="asc" />
          </el-select>
          <span class="sep">+</span>
          <el-select v-model="query.secondary_sort" style="width: 130px" :disabled="!query.primary_sort" @change="search">
            <el-option label="无" value="" />
            <el-option label="活跃值" value="activity_score" />
            <el-option label="发布时间" value="publish_time" />
          </el-select>
          <el-select v-model="query.secondary_dir" style="width: 90px" :disabled="!query.primary_sort" @change="search">
            <el-option label="降序" value="desc" />
            <el-option label="升序" value="asc" />
          </el-select>
        </el-form-item>
        <el-form-item label="发布时间">
          <el-date-picker
            v-model="publishRange"
            type="daterange"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            :shortcuts="dateShortcuts"
            style="width: 240px"
            @change="search"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <el-table :data="page.items" v-loading="loading" @row-click="openDetail">
        <el-table-column prop="title" label="职位" min-width="220" show-overflow-tooltip />
        <el-table-column label="公司" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.company_name ?? row.company_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="活跃度" width="110">
          <template #default="{ row }">{{ row.company_activity ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="活跃值" width="90" align="center">
          <template #default="{ row }">
            <span :class="scoreClass(row.company_activity_score)">{{ row.company_activity_score ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="城市" width="110">
          <template #default="{ row }">{{ row.city ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="区域" width="110">
          <template #default="{ row }">{{ row.district ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="薪资" width="130">
          <template #default="{ row }">{{ formatSalaryRaw(row.salary_raw) }}</template>
        </el-table-column>
        <el-table-column label="学历" width="90">
          <template #default="{ row }">{{ row.degree ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="工作年限" width="110">
          <template #default="{ row }">{{ row.year ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="标签" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="t in (row.tags ?? [])" :key="t" size="small" class="tag">{{ t }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" width="150">
          <template #default="{ row }">{{ formatTime(row.publish_time) }}</template>
        </el-table-column>
        <el-table-column label="入库时间" width="150">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="page.total"
        :page-size="query.page_size"
        :current-page="query.page"
        @current-change="onPage"
      />
    </el-card>

    <JobDetailDialog v-model="detailVisible" :job="detailJob" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { jobsApi, type JobOut, type JobPage, type JobQuery } from '@/api/jobs'
import { formatSalaryRaw, formatTime } from '@/utils/format'
import JobDetailDialog from '@/components/JobDetailDialog.vue'

const loading = ref(false)
const page = ref<JobPage>({ total: 0, items: [] })
const detailVisible = ref(false)
const detailJob = ref<JobOut | null>(null)
const cityOptions = ref<string[]>([])
const districtOptions = ref<string[]>([])
const publishRange = ref<[string, string] | null>(null)

function daysAgo(n: number): Date {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d
}

const dateShortcuts: Array<{ text: string; value: () => [Date, Date] }> = [
  { text: '今天', value: () => [new Date(), new Date()] },
  { text: '近7天', value: () => [daysAgo(6), new Date()] },
  { text: '近30天', value: () => [daysAgo(29), new Date()] },
  { text: '近90天', value: () => [daysAgo(89), new Date()] },
]

const query = reactive<{
  page: number
  page_size: number
  keyword: string
  city: string
  district: string
  company_id: string
  tag: string
  salary_min: number | undefined
  salary_max: number | undefined
  primary_sort: '' | 'activity_score' | 'publish_time'
  primary_dir: 'asc' | 'desc'
  secondary_sort: '' | 'activity_score' | 'publish_time'
  secondary_dir: 'asc' | 'desc'
}>({
  page: 1,
  page_size: 20,
  keyword: '',
  city: '',
  district: '',
  company_id: '',
  tag: '',
  salary_min: undefined,
  salary_max: undefined,
  primary_sort: '',
  primary_dir: 'desc',
  secondary_sort: '',
  secondary_dir: 'desc',
})

async function load() {
  loading.value = true
  try {
    const params: JobQuery = { page: query.page, page_size: query.page_size }
    if (query.keyword) params.keyword = query.keyword
    if (query.city) params.city = query.city
    if (query.district) params.district = query.district
    if (query.company_id) params.company_id = query.company_id
    if (query.tag) params.tag = query.tag
    if (query.salary_min != null) params.salary_min = query.salary_min
    if (query.salary_max != null) params.salary_max = query.salary_max
    if (publishRange.value) {
      params.publish_time_from = publishRange.value[0]
      params.publish_time_to = publishRange.value[1]
    }
    if (query.primary_sort) {
      params.sort = [`${query.primary_sort}:${query.primary_dir}`]
      if (query.secondary_sort) params.sort.push(`${query.secondary_sort}:${query.secondary_dir}`)
    }
    page.value = await jobsApi.list(params)
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function loadFilterOptions() {
  try {
    const opts = await jobsApi.filterOptions(query.city)
    cityOptions.value = opts.cities
    districtOptions.value = opts.districts
  } catch {
    // 拦截器已提示
  }
}

function onCityChange() {
  query.district = ''
  loadFilterOptions()
  search()
}

function search() {
  query.page = 1
  load()
}

function reset() {
  query.keyword = ''
  query.city = ''
  query.district = ''
  query.company_id = ''
  query.tag = ''
  query.salary_min = undefined
  query.salary_max = undefined
  query.primary_sort = ''
  query.primary_dir = 'desc'
  query.secondary_sort = ''
  query.secondary_dir = 'desc'
  publishRange.value = null
  loadFilterOptions()
  search()
}

function onPage(p: number) {
  query.page = p
  load()
}

async function openDetail(row: JobOut) {
  try {
    detailJob.value = await jobsApi.get(row.job_id)
    detailVisible.value = true
  } catch {
    // 拦截器已提示
  }
}

function scoreClass(score: number | undefined): string {
  if (score == null || score < 0) return 'score-unknown'
  if (score >= 8) return 'score-high'
  if (score >= 5) return 'score-mid'
  return 'score-low'
}

onMounted(() => {
  loadFilterOptions()
  load()
})
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.sep { margin: 0 8px; color: var(--el-text-color-secondary); }
.tag { margin-right: 4px; }
.score-high { color: #f56c6c; font-weight: 600; }
.score-mid { color: #e6a23c; font-weight: 600; }
.score-low { color: #909399; }
.score-unknown { color: #ffffff; }
</style>
