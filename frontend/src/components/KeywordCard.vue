<template>
  <el-card class="keyword-card" shadow="hover">
    <div class="keyword-header">
      <span class="keyword-name">{{ kw.keyword }}</span>
      <el-switch :model-value="kw.enabled" @change="emit('toggle')" />
    </div>
    <div class="keyword-meta">
      <span class="meta-item">{{ cityName(kw.city) }}</span>
      <span v-if="kw.industry" class="meta-item">{{ industryNames(kw.industry) }}</span>
      <span class="meta-item">{{ kw.scrape_mode }}</span>
      <span class="meta-item">最近抓取 {{ formatTime(kw.last_scraped_at) }}</span>
    </div>
    <div class="keyword-actions">
      <el-button size="small" @click="emit('edit')">编辑</el-button>
      <el-button size="small" type="danger" @click="emit('remove')">删除</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { KeywordOut } from '@/api/keywords'
import { cityName } from '@/utils/cities'
import { industryNames } from '@/utils/industries'
import { formatTime } from '@/utils/format'

defineProps<{ kw: KeywordOut }>()
const emit = defineEmits<{ toggle: []; edit: []; remove: [] }>()
</script>

<style scoped>
.keyword-card { margin-bottom: 10px; }
.keyword-header { display: flex; align-items: center; gap: 8px; }
.keyword-name { flex: 1; font-size: 15px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.keyword-meta {
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
.keyword-actions { margin-top: 8px; }
</style>
