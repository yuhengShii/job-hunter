<template>
  <div>
    <el-card v-if="!isMobile" class="filter-card">
      <JobFilters
        mode="inline"
        :state="query"
        :city-options="cityOptions"
        :district-options="districtOptions"
        @search="search"
        @reset="reset"
        @city-change="onCityChange"
      />
    </el-card>

    <el-card>
      <div class="toolbar">
        <span class="selected-info">已选 {{ selection.length }} 项</span>
        <el-button type="primary" :disabled="selection.length === 0" @click="batchFavorite(true)">批量收藏</el-button>
        <el-button :disabled="selection.length === 0" @click="batchFavorite(false)">批量取消收藏</el-button>
      </div>
      <el-table :data="page.items" v-loading="loading" @selection-change="onSelectionChange" @row-click="onRowClick">
        <el-table-column type="selection" width="40" />
        <el-table-column label="收藏" width="70" align="center">
          <template #default="{ row }">
            <el-button link :type="row.is_favorite ? 'warning' : 'info'" @click.stop="toggleFavorite(row)">
              <el-icon :size="16"><StarFilled v-if="row.is_favorite" /><Star v-else /></el-icon>
            </el-button>
          </template>
        </el-table-column>
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
import { useRoute, useRouter } from 'vue-router'
import { Star, StarFilled } from '@element-plus/icons-vue'
import { jobsApi, type JobOut, type JobPage, type JobQuery } from '@/api/jobs'
import { formatSalaryRaw, formatTime } from '@/utils/format'
import { favoriteParam, jobsStateFromRoute } from '@/utils/jobsQuery'
import JobDetailDialog from '@/components/JobDetailDialog.vue'
import JobFilters, { createDefaultJobFilterState, type JobFilterState } from './JobFilters.vue'
import { useIsMobile } from '@/composables/useIsMobile'

const route = useRoute()
const router = useRouter()
const isMobile = useIsMobile()

const loading = ref(false)
const page = ref<JobPage>({ total: 0, items: [] })
const detailVisible = ref(false)
const detailJob = ref<JobOut | null>(null)
const cityOptions = ref<string[]>([])
const districtOptions = ref<string[]>([])
const selection = ref<JobOut[]>([])

const query = reactive<JobFilterState>(createDefaultJobFilterState())

async function load() {
  loading.value = true
  try {
    const params: JobQuery = { page: query.page, page_size: query.page_size }
    if (query.keyword) params.keyword = query.keyword
    if (query.city) params.city = query.city
    if (query.district) params.district = query.district
    if (query.area) params.area = query.area
    if (query.company_id) params.company_id = query.company_id
    if (query.tag) params.tag = query.tag
    const fav = favoriteParam(query.favorite)
    if (fav !== undefined) params.favorite = fav
    if (query.salary_min != null) params.salary_min = query.salary_min
    if (query.salary_max != null) params.salary_max = query.salary_max
    if (query.publishRange) {
      params.publish_time_from = query.publishRange[0]
      params.publish_time_to = query.publishRange[1]
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
  Object.assign(query, createDefaultJobFilterState())
  router.replace({ path: '/jobs' })
  loadFilterOptions()
  search()
}

function onPage(p: number) {
  query.page = p
  load()
}

function onRowClick(row: JobOut, column: { type?: string }) {
  if (column.type === 'selection') return
  openDetail(row)
}

function onSelectionChange(rows: JobOut[]) {
  selection.value = rows
}

async function toggleFavorite(row: JobOut) {
  try {
    if (row.is_favorite) {
      await jobsApi.removeFavorites([row.job_id])
    } else {
      await jobsApi.addFavorites([row.job_id])
    }
    load()
  } catch {
    // 拦截器已提示
  }
}

async function batchFavorite(add: boolean) {
  const ids = selection.value.map((r) => r.job_id)
  if (ids.length === 0) return
  try {
    if (add) {
      await jobsApi.addFavorites(ids)
    } else {
      await jobsApi.removeFavorites(ids)
    }
    selection.value = []
    load()
  } catch {
    // 拦截器已提示
  }
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
  const s = jobsStateFromRoute(route.query as Record<string, unknown>)
  query.city = s.city
  query.district = s.district
  query.area = s.area
  query.keyword = s.keyword
  query.publishRange = s.publishRange
  loadFilterOptions()
  load()
})
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.toolbar { margin-bottom: 12px; }
.selected-info { margin-right: 12px; color: var(--el-text-color-secondary); }
.pager { margin-top: 16px; justify-content: flex-end; }
.sep { margin: 0 8px; color: var(--el-text-color-secondary); }
.tag { margin-right: 4px; }
.score-high { color: #f56c6c; font-weight: 600; }
.score-mid { color: #e6a23c; font-weight: 600; }
.score-low { color: #909399; }
.score-unknown { color: #ffffff; }
</style>
