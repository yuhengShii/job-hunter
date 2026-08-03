<template>
  <div>
    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="关键字">
          <el-input v-model="query.keyword" clearable placeholder="职位/地区包含" style="width: 180px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="城市">
          <el-input v-model="query.city" clearable style="width: 140px" @keyup.enter="search" />
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
        <el-table-column label="城市" width="110">
          <template #default="{ row }">{{ row.city ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="区域" width="110">
          <template #default="{ row }">{{ row.district ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="薪资" width="130">
          <template #default="{ row }">{{ formatSalaryRaw(row.salary_raw) }}</template>
        </el-table-column>
        <el-table-column label="标签" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="t in (row.tags ?? [])" :key="t" size="small" class="tag">{{ t }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" width="150">
          <template #default="{ row }">{{ formatTime(row.publish_time) }}</template>
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

const query = reactive<{
  page: number
  page_size: number
  keyword: string
  city: string
  company_id: string
  tag: string
  salary_min: number | undefined
  salary_max: number | undefined
}>({
  page: 1,
  page_size: 20,
  keyword: '',
  city: '',
  company_id: '',
  tag: '',
  salary_min: undefined,
  salary_max: undefined,
})

async function load() {
  loading.value = true
  try {
    const params: JobQuery = { page: query.page, page_size: query.page_size }
    if (query.keyword) params.keyword = query.keyword
    if (query.city) params.city = query.city
    if (query.company_id) params.company_id = query.company_id
    if (query.tag) params.tag = query.tag
    if (query.salary_min != null) params.salary_min = query.salary_min
    if (query.salary_max != null) params.salary_max = query.salary_max
    page.value = await jobsApi.list(params)
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function search() {
  query.page = 1
  load()
}

function reset() {
  query.keyword = ''
  query.city = ''
  query.company_id = ''
  query.tag = ''
  query.salary_min = undefined
  query.salary_max = undefined
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

onMounted(load)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.sep { margin: 0 8px; color: var(--el-text-color-secondary); }
.tag { margin-right: 4px; }
</style>
