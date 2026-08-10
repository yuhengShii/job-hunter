<template>
  <el-dialog
    :model-value="modelValue"
    :title="job?.title ?? '职位详情'"
    width="640px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-descriptions v-if="job" :column="2" border>
      <el-descriptions-item label="职位">{{ job.title }}</el-descriptions-item>
      <el-descriptions-item label="薪资">
        {{ formatSalaryParsed(job.salary_min, job.salary_max) }}（{{ formatSalaryRaw(job.salary_raw) }}）
      </el-descriptions-item>
      <el-descriptions-item label="城市">{{ job.city ?? '-' }}</el-descriptions-item>
      <el-descriptions-item label="区域">{{ job.area ?? '-' }}</el-descriptions-item>
      <el-descriptions-item label="公司">{{ companyName }}</el-descriptions-item>
      <el-descriptions-item label="标签">{{ (job.tags ?? []).join('、') || '-' }}</el-descriptions-item>
      <el-descriptions-item label="发布时间">{{ formatTime(job.publish_time) }}</el-descriptions-item>
      <el-descriptions-item label="来源">{{ job.source }}</el-descriptions-item>
      <el-descriptions-item label="链接" :span="2">
        <el-link v-if="job.job_url" :href="job.job_url" target="_blank">{{ job.job_url }}</el-link>
        <span v-else>-</span>
      </el-descriptions-item>
      <el-descriptions-item label="职位 ID">{{ job.job_id }}</el-descriptions-item>
      <el-descriptions-item label="公司 ID">{{ job.company_id ?? '-' }}</el-descriptions-item>
      <el-descriptions-item label="更新时间">{{ formatTime(job.updated_at) }}</el-descriptions-item>
    </el-descriptions>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { JobOut } from '@/api/jobs'
import { formatSalaryParsed, formatSalaryRaw, formatTime } from '@/utils/format'

const props = defineProps<{ modelValue: boolean; job: JobOut | null }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

// 公司名称/活跃度已由详情接口附带（company_name），无需再全量拉取 companies 表
const companyName = computed(() => props.job?.company_name ?? props.job?.company_id ?? '-')
</script>
