<template>
  <el-card class="job-card" :class="{ 'is-selected': selected }" shadow="hover" @click="emit('click')">
    <div class="job-card-header">
      <el-checkbox
        v-if="selectable"
        class="job-check"
        :model-value="selected"
        @click.stop
        @change="(v: string | number | boolean) => emit('select', Boolean(v))"
      />
      <span class="job-title">{{ job.title }}</span>
      <el-tag v-if="job.applied" type="success" size="small" effect="light" class="applied-tag">已投递</el-tag>
      <span class="job-salary">{{ formatSalaryRaw(job.salary_raw) }}</span>
    </div>
    <div class="job-card-company">
      <el-icon class="company-icon"><OfficeBuilding /></el-icon>
      <span class="company-name">{{ job.company_name ?? job.company_id ?? '-' }}</span>
      <el-button
        class="fav-btn"
        link
        :type="job.is_favorite ? 'warning' : 'info'"
        @click.stop="emit('toggle-favorite')"
      >
        <el-icon :size="16"><StarFilled v-if="job.is_favorite" /><Star v-else /></el-icon>
      </el-button>
    </div>
    <div class="job-card-meta">
      <span>{{ job.city ?? '-' }}{{ job.district ? ` · ${job.district}` : '' }}</span>
      <span v-if="job.degree || job.year">{{ job.degree ?? '-' }} · {{ job.year ?? '-' }}</span>
      <span v-if="job.company_activity">{{ job.company_activity }}</span>
      <span>{{ formatTime(job.publish_time) }}</span>
    </div>
    <div v-if="(job.tags ?? []).length" class="job-card-tags">
      <el-tag v-for="t in job.tags" :key="t" size="small" class="tag">{{ t }}</el-tag>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { Star, StarFilled, OfficeBuilding } from '@element-plus/icons-vue'
import type { JobOut } from '@/api/jobs'
import { formatSalaryRaw, formatTime } from '@/utils/format'

defineProps<{ job: JobOut; selectable?: boolean; selected?: boolean }>()
const emit = defineEmits<{ click: []; 'toggle-favorite': []; select: [boolean] }>()
</script>

<style scoped>
.job-card { margin-bottom: 10px; cursor: pointer; }
.job-card.is-selected { outline: 1px solid var(--el-color-primary); }
.job-card-header { display: flex; align-items: center; gap: 8px; }
.job-check { margin-right: 2px; }
.job-title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.job-salary { color: #f56c6c; font-weight: 600; white-space: nowrap; }
.applied-tag { flex-shrink: 0; }
.job-card-company {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.company-icon { color: var(--el-text-color-secondary); }
.company-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fav-btn { flex-shrink: 0; }
.job-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.job-card-tags { margin-top: 8px; }
.tag { margin-right: 4px; }
</style>
