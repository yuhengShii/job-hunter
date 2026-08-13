<template>
  <el-card class="company-card" shadow="hover">
    <div class="company-header">
      <span class="company-name">{{ company.name }}</span>
      <el-tag v-if="company.type" size="small" :type="typeTagType(company.type)">{{ company.type }}</el-tag>
    </div>
    <div class="company-meta">
      <span v-if="company.industry" class="meta-item">{{ company.industry }}</span>
      <span v-if="company.size" class="meta-item">{{ company.size }}</span>
      <span v-if="company.activity" class="meta-item">{{ company.activity }}</span>
    </div>
    <div class="company-footer">更新于 {{ formatTime(company.updated_at) }}</div>
  </el-card>
</template>

<script setup lang="ts">
import type { CompanyOut } from '@/api/companies'
import { formatTime } from '@/utils/format'

defineProps<{ company: CompanyOut }>()

function typeTagType(t: string): '' | 'success' | 'warning' {
  if (t === '国企') return 'success'
  if (t === '外企') return 'warning'
  return ''
}
</script>

<style scoped>
.company-card { margin-bottom: 10px; }
.company-header { display: flex; align-items: center; gap: 8px; }
.company-name { flex: 1; font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.company-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.meta-item {
  padding: 1px 6px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.company-footer { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
</style>
