<template>
  <div>
    <el-card class="filter-card">
      <div class="toolbar">
        <span class="hint">对收藏的职位在后台逐个自动登录投递，结果逐条可见。</span>
        <el-button type="primary" @click="dialogVisible = true">一键投递全部收藏</el-button>
      </div>
    </el-card>

    <el-card>
      <el-table v-if="!isMobile" :data="tasks" v-loading="loading" row-key="id">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="results">
              <div v-for="r in row.results" :key="r.job_id" class="result-row">
                <el-tag :type="resultType(r.status)" size="small">{{ resultText(r.status) }}</el-tag>
                <span class="result-title">{{ r.title }}</span>
                <span class="result-msg">{{ r.message || '-' }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="taskStatusType(row.status)">{{ taskStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }">
            成功 {{ row.success_count }} / 失败 {{ row.failed_count }} / 跳过 {{ row.skipped_count }}（共 {{ row.total_count }}）
          </template>
        </el-table-column>
        <el-table-column label="账号" width="150">
          <template #default="{ row }">{{ row.credential_username || '-' }}</template>
        </el-table-column>
        <el-table-column label="开始 / 结束" width="200">
          <template #default="{ row }">{{ formatTime(row.start_time) }} / {{ formatTime(row.end_time) }}</template>
        </el-table-column>
        <el-table-column label="错误" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_message ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-else class="mobile-list" v-loading="loading">
        <el-card v-for="t in tasks" :key="t.id" class="mobile-item">
          <div class="mobile-head">
            <el-tag :type="taskStatusType(t.status)">{{ taskStatusText(t.status) }}</el-tag>
            <span class="hint">{{ t.credential_username || '-' }}</span>
          </div>
          <div>成功 {{ t.success_count }} / 失败 {{ t.failed_count }} / 跳过 {{ t.skipped_count }}（共 {{ t.total_count }}）</div>
          <div class="hint">{{ formatTime(t.start_time) }} / {{ formatTime(t.end_time) }}</div>
          <div v-if="t.error_message" class="hint">{{ t.error_message }}</div>
          <div class="results">
            <div v-for="r in t.results" :key="r.job_id" class="result-row">
              <el-tag :type="resultType(r.status)" size="small">{{ resultText(r.status) }}</el-tag>
              <span class="result-title">{{ r.title }}</span>
            </div>
          </div>
          <el-button size="small" @click="remove(t)">删除</el-button>
        </el-card>
      </div>
    </el-card>

    <ApplyDialog
      v-model="dialogVisible"
      :credentials="credentials"
      :favorite-count="favoriteCount"
      :selected-count="0"
      @create="createTask"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { applyApi, type ApplyTaskOut } from '@/api/apply'
import { jobsApi } from '@/api/jobs'
import { siteCredentialsApi, type SiteCredentialOut } from '@/api/siteCredentials'
import { formatTime, taskStatusText, taskStatusType } from '@/utils/format'
import { useIsMobile } from '@/composables/useIsMobile'
import ApplyDialog from '@/components/ApplyDialog.vue'

const isMobile = useIsMobile()
const loading = ref(false)
const tasks = ref<ApplyTaskOut[]>([])
const credentials = ref<SiteCredentialOut[]>([])
const favoriteCount = ref(0)
const dialogVisible = ref(false)

const RESULT_TEXT: Record<string, string> = {
  pending: '待投递',
  success: '成功',
  failed: '失败',
  skipped: '已投递',
}
const RESULT_TYPE: Record<string, 'info' | 'success' | 'danger' | 'warning'> = {
  pending: 'info',
  success: 'success',
  failed: 'danger',
  skipped: 'warning',
}

function resultText(s: string): string {
  return RESULT_TEXT[s] ?? s
}
function resultType(s: string): 'info' | 'success' | 'danger' | 'warning' {
  return RESULT_TYPE[s] ?? 'info'
}

async function load() {
  loading.value = true
  try {
    tasks.value = await applyApi.list()
  } finally {
    loading.value = false
  }
}

async function loadCredentials() {
  try {
    credentials.value = (await siteCredentialsApi.list()).filter((c) => c.site === '51job')
  } catch {
    // 拦截器已提示
  }
}

async function loadFavoriteCount() {
  try {
    const page = await jobsApi.list({ favorite: true, page_size: 1 })
    favoriteCount.value = page.total
  } catch {
    // 拦截器已提示
  }
}

async function createTask(payload: { credential_id: number; scope: 'favorites' | 'selected' }) {
  try {
    await applyApi.create({ credential_id: payload.credential_id, job_ids: null })
    ElMessage.success('投递任务已创建')
    dialogVisible.value = false
    await load()
  } catch {
    // 拦截器已提示（409 冲突等）
  }
}

async function remove(row: ApplyTaskOut) {
  try {
    await ElMessageBox.confirm(`确认删除投递任务 #${row.id}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await applyApi.remove(row.id)
    await load()
  } catch {
    // 拦截器已提示
  }
}

let pollTimer: number | undefined

onMounted(async () => {
  try {
    await Promise.all([load(), loadCredentials(), loadFavoriteCount()])
  } catch {
    // 拦截器已提示
  }
  pollTimer = window.setInterval(async () => {
    if (tasks.value.some((t) => t.status === 'in_progress' || t.status === 'queued')) {
      try {
        await load()
      } catch {
        // 拦截器已提示
      }
    }
  }, 3000)
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; }
.hint { color: var(--el-text-color-secondary); font-size: 12px; }
.results { padding: 8px 16px; }
.result-row { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.result-title { flex: 0 0 auto; }
.result-msg { color: var(--el-text-color-secondary); font-size: 12px; }
.mobile-list { min-height: 60px; }
.mobile-item { margin-bottom: 12px; }
.mobile-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
</style>
