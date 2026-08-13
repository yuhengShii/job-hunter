<template>
  <el-card class="task-card" shadow="hover">
    <div class="task-header">
      <span class="task-keyword">{{ keywordName }}</span>
      <el-tag :type="taskStatusType(task.status)">{{ taskStatusText(task.status) }}</el-tag>
    </div>
    <div v-if="task.status === 'queued' || task.status === 'in_progress'" class="task-progress">
      <div class="progress-text">
        已抓 {{ task.last_page }} 页{{ task.total_pages ? ` / 共 ${task.total_pages} 页` : '' }}
      </div>
      <el-progress v-if="task.total_pages" :percentage="progressPct" :stroke-width="6" />
    </div>
    <div v-else-if="task.status === 'success' || task.status === 'partial_success'" class="task-progress">
      成功 {{ task.success_count }} / 失败 {{ task.failed_count }}（共 {{ task.total_pages ?? '-' }} 页）
    </div>
    <div v-else class="task-progress">{{ task.error_message ?? '-' }}</div>
    <div v-if="loginUsername" class="task-login">已登录：{{ loginUsername }}</div>
    <div class="task-time">{{ formatTime(task.start_time) }} / {{ formatTime(task.end_time) }}</div>
    <div class="task-actions">
      <el-button size="small" type="danger" @click="emit('remove')">删除</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskOut } from '@/api/tasks'
import { formatTime, taskStatusText, taskStatusType } from '@/utils/format'

const props = defineProps<{ task: TaskOut; keywordName: string; loginUsername?: string }>()
const emit = defineEmits<{ remove: [] }>()

const progressPct = computed(() => {
  if (!props.task.total_pages) return 0
  return Math.min(100, Math.round((props.task.last_page / props.task.total_pages) * 100))
})
</script>

<style scoped>
.task-card { margin-bottom: 10px; }
.task-header { display: flex; align-items: center; gap: 8px; }
.task-keyword { flex: 1; font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-progress { margin-top: 8px; font-size: 13px; color: var(--el-text-color-regular); }
.progress-text { margin-bottom: 4px; }
.task-time { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.task-login { margin-top: 6px; font-size: 12px; color: var(--el-color-warning); }
.task-actions { margin-top: 8px; }
</style>
