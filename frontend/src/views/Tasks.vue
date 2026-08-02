<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="16">
        <el-card class="section-card">
          <template #header>
            <div class="card-header">
              <span>关键字管理</span>
              <el-button type="primary" size="small" @click="openCreate">新建关键字</el-button>
            </div>
          </template>
          <el-table :data="keywordsStore.list" v-loading="keywordsStore.loading">
            <el-table-column prop="keyword" label="关键字" min-width="140" />
            <el-table-column label="启用" width="80">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" @change="toggle(row)" />
              </template>
            </el-table-column>
            <el-table-column prop="scrape_mode" label="抓取方式" width="110" />
            <el-table-column label="最近抓取" width="160">
              <template #default="{ row }">{{ formatTime(row.last_scraped_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button size="small" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="removeKeyword(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card class="section-card">
          <template #header>新建抓取任务</template>
          <el-form inline>
            <el-form-item label="关键字">
              <el-select v-model="taskForm.keyword_id" placeholder="选择关键字" style="width: 200px">
                <el-option v-for="kw in keywordsStore.list" :key="kw.id" :label="kw.keyword" :value="kw.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="方式">
              <el-select v-model="taskForm.mode" style="width: 140px">
                <el-option label="Playwright" value="playwright" />
              </el-select>
            </el-form-item>
            <el-form-item label="最大页数">
              <el-input-number v-model="taskForm.max_pages" :min="1" :max="1000" placeholder="留空用默认" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="creating" @click="createTask">创建任务</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="section-card">
          <template #header>任务列表</template>
          <el-table :data="tasks" v-loading="tasksLoading">
            <el-table-column label="关键字" width="120">
              <template #default="{ row }">{{ keywordName(row.keyword_id) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="taskStatusType(row.status)">{{ taskStatusText(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="进度" min-width="220">
              <template #default="{ row }">
                <div v-if="row.status === 'queued' || row.status === 'in_progress'">
                  <span>已抓 {{ row.last_page }} 页{{ row.total_pages ? ` / 共 ${row.total_pages} 页` : '' }}</span>
                  <el-progress v-if="row.total_pages" :percentage="progressPct(row)" :stroke-width="6" />
                </div>
                <span v-else-if="row.status === 'success' || row.status === 'partial_success'">
                  成功 {{ row.success_count }} / 失败 {{ row.failed_count }}（共 {{ row.total_pages ?? '-' }} 页）
                </span>
                <span v-else>{{ row.error_message ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="开始 / 结束" width="200">
              <template #default="{ row }">{{ formatTime(row.start_time) }} / {{ formatTime(row.end_time) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" @click="removeTask(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card>
          <template #header>定时任务设置</template>
          <el-form label-width="110px">
            <el-form-item label="启用定时">
              <el-switch v-model="schedule.enabled" @change="saveSchedule" />
            </el-form-item>
            <el-form-item label="间隔（分钟）">
              <el-input-number v-model="schedule.interval_minutes" :min="5" :max="1440" :disabled="!schedule.enabled" @change="saveSchedule" />
            </el-form-item>
            <el-form-item label="目标关键字">
              <el-select
                v-model="schedule.keyword_ids"
                multiple
                style="width: 100%"
                :disabled="!schedule.enabled"
                placeholder="选择要定时抓取的关键字"
                @change="saveSchedule"
              >
                <el-option v-for="kw in keywordsStore.list" :key="kw.id" :label="kw.keyword" :value="kw.id" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="keywordDialog.visible" :title="keywordDialog.editing ? '编辑关键字' : '新建关键字'" width="420px">
      <el-form label-width="80px">
        <el-form-item label="关键字">
          <el-input v-model="keywordDialog.keyword" />
        </el-form-item>
        <el-form-item label="抓取方式">
          <el-select v-model="keywordDialog.scrape_mode" style="width: 100%">
            <el-option label="Playwright" value="playwright" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="keywordDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveKeyword">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { keywordsApi, type KeywordOut } from '@/api/keywords'
import { tasksApi, type TaskOut } from '@/api/tasks'
import { settingsApi, type ScheduleOut } from '@/api/settings'
import { useKeywordsStore } from '@/stores/keywords'
import { formatTime, taskStatusText, taskStatusType } from '@/utils/format'

const keywordsStore = useKeywordsStore()
const tasks = ref<TaskOut[]>([])
const tasksLoading = ref(false)
const creating = ref(false)
const schedule = ref<ScheduleOut>({ enabled: false, interval_minutes: 60, keyword_ids: [] })

const taskForm = reactive<{ keyword_id: number | null; mode: string; max_pages: number | null }>({
  keyword_id: null,
  mode: 'playwright',
  max_pages: null,
})

const keywordDialog = reactive({
  visible: false,
  editing: false,
  id: 0,
  keyword: '',
  scrape_mode: 'playwright',
})

let pollTimer: number | undefined

function keywordName(id: number): string {
  return keywordsStore.list.find((k) => k.id === id)?.keyword ?? `#${id}`
}

function progressPct(row: TaskOut): number {
  if (!row.total_pages) return 0
  return Math.min(100, Math.round((row.last_page / row.total_pages) * 100))
}

async function loadTasks() {
  tasksLoading.value = true
  try {
    tasks.value = await tasksApi.list()
  } finally {
    tasksLoading.value = false
  }
}

async function loadSchedule() {
  schedule.value = await settingsApi.getSchedule()
}

async function saveSchedule() {
  try {
    await settingsApi.updateSchedule(schedule.value)
    ElMessage.success('定时设置已保存')
  } catch {
    // 拦截器已提示
  }
}

async function createTask() {
  if (taskForm.keyword_id == null) {
    ElMessage.warning('请选择关键字')
    return
  }
  creating.value = true
  try {
    await tasksApi.create({
      keyword_id: taskForm.keyword_id,
      mode: taskForm.mode,
      max_pages: taskForm.max_pages,
    })
    ElMessage.success('任务已创建')
    await loadTasks()
  } catch {
    // 拦截器已提示（含 409 冲突说明）
  } finally {
    creating.value = false
  }
}

async function removeTask(row: TaskOut) {
  try {
    await ElMessageBox.confirm(`确认删除任务 #${row.id}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await tasksApi.remove(row.id)
    await loadTasks()
  } catch {
    // 拦截器已提示（进行中的任务 400）
  }
}

function openCreate() {
  keywordDialog.editing = false
  keywordDialog.id = 0
  keywordDialog.keyword = ''
  keywordDialog.scrape_mode = 'playwright'
  keywordDialog.visible = true
}

function openEdit(row: KeywordOut) {
  keywordDialog.editing = true
  keywordDialog.id = row.id
  keywordDialog.keyword = row.keyword
  keywordDialog.scrape_mode = row.scrape_mode
  keywordDialog.visible = true
}

async function saveKeyword() {
  const kw = keywordDialog.keyword.trim()
  if (!kw) {
    ElMessage.warning('请输入关键字')
    return
  }
  try {
    if (keywordDialog.editing) {
      await keywordsApi.update(keywordDialog.id, { keyword: kw, scrape_mode: keywordDialog.scrape_mode })
    } else {
      await keywordsApi.create({ keyword: kw, scrape_mode: keywordDialog.scrape_mode })
    }
    keywordDialog.visible = false
    await keywordsStore.fetch()
  } catch {
    // 拦截器已提示（重复 409）
  }
}

async function toggle(row: KeywordOut) {
  try {
    await keywordsApi.toggle(row.id)
    await keywordsStore.fetch()
  } catch {
    // 拦截器已提示
  }
}

async function removeKeyword(row: KeywordOut) {
  try {
    await ElMessageBox.confirm(`确认删除关键字「${row.keyword}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await keywordsApi.remove(row.id)
    await keywordsStore.fetch()
  } catch {
    // 拦截器已提示
  }
}

onMounted(async () => {
  try {
    await Promise.all([keywordsStore.fetch(), loadTasks(), loadSchedule()])
  } catch {
    // 拦截器已提示
  }
  pollTimer = window.setInterval(async () => {
    if (tasks.value.some((t) => t.status === 'in_progress' || t.status === 'queued')) {
      try {
        await loadTasks()
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
.section-card { margin-bottom: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
