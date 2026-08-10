<template>
  <div>
    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="类型">
          <el-input v-model="query.type" clearable placeholder="如 民营" style="width: 140px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="query.industry" clearable placeholder="包含匹配" style="width: 180px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="规模">
          <el-input v-model="query.size" clearable placeholder="如 1000-4999人" style="width: 160px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <el-table :data="page.items" v-loading="loading">
        <el-table-column prop="name" label="公司名称" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ row.type ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="industry" label="行业" min-width="160" show-overflow-tooltip />
        <el-table-column label="规模" width="130">
          <template #default="{ row }">{{ row.size ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="活跃度" width="100">
          <template #default="{ row }">{{ row.activity ?? '-' }}</template>
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { companiesApi, type CompanyPage } from '@/api/companies'
import { formatTime } from '@/utils/format'

const loading = ref(false)
const page = ref<CompanyPage>({ total: 0, items: [] })

const query = reactive<{
  page: number
  page_size: number
  type: string
  industry: string
  size: string
}>({
  page: 1,
  page_size: 20,
  type: '',
  industry: '',
  size: '',
})

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, page_size: query.page_size }
    if (query.type) Object.assign(params, { type: query.type })
    if (query.industry) Object.assign(params, { industry: query.industry })
    if (query.size) Object.assign(params, { size: query.size })
    page.value = await companiesApi.list(params)
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
  query.type = ''
  query.industry = ''
  query.size = ''
  search()
}

function onPage(p: number) {
  query.page = p
  load()
}

onMounted(load)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>
