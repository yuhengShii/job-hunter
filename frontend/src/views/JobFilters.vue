<template>
  <el-form
    :inline="mode === 'inline'"
    :label-position="mode === 'stack' ? 'top' : undefined"
    @submit.prevent
  >
    <el-form-item label="关键字">
      <el-input
        v-model="state.keyword"
        clearable
        placeholder="职位/地区包含"
        :style="ctl('180px')"
        @keyup.enter="emit('search')"
      />
    </el-form-item>
    <el-form-item label="城市">
      <el-select
        v-model="state.city"
        clearable
        placeholder="全部"
        :style="ctl('140px')"
        @change="emit('city-change')"
      >
        <el-option v-for="c in cityOptions" :key="c" :label="c" :value="c" />
      </el-select>
    </el-form-item>
    <el-form-item label="区域">
      <el-select
        v-model="state.district"
        clearable
        placeholder="全部"
        :style="ctl('140px')"
        :disabled="districtOptions.length === 0"
        @change="emit('search')"
      >
        <el-option v-for="d in districtOptions" :key="d" :label="d" :value="d" />
      </el-select>
    </el-form-item>
    <el-form-item label="地区">
      <el-input
        v-model="state.area"
        clearable
        placeholder="如 上海-长宁区"
        :style="ctl('160px')"
        @keyup.enter="emit('search')"
      />
    </el-form-item>
    <el-form-item label="公司">
      <el-input
        v-model="state.company_id"
        clearable
        placeholder="公司 ID"
        :style="ctl('160px')"
        @keyup.enter="emit('search')"
      />
    </el-form-item>
    <el-form-item label="标签">
      <el-input v-model="state.tag" clearable :style="ctl('140px')" @keyup.enter="emit('search')" />
    </el-form-item>
    <el-form-item label="收藏">
      <el-select v-model="state.favorite" :style="ctl('120px')" @change="emit('search')">
        <el-option label="全部" value="" />
        <el-option label="已收藏" value="yes" />
        <el-option label="未收藏" value="no" />
      </el-select>
    </el-form-item>
    <el-form-item label="薪资区间">
      <el-input-number
        v-model="state.salary_min"
        :min="0"
        :step="1000"
        placeholder="最低"
        @change="emit('search')"
      />
      <span class="sep">~</span>
      <el-input-number
        v-model="state.salary_max"
        :min="0"
        :step="1000"
        placeholder="最高"
        @change="emit('search')"
      />
    </el-form-item>
    <el-form-item label="排序">
      <el-select v-model="state.primary_sort" :style="ctl('130px')" @change="emit('search')">
        <el-option label="默认" value="" />
        <el-option label="活跃值" value="activity_score" />
        <el-option label="发布时间" value="publish_time" />
      </el-select>
      <el-select
        v-model="state.primary_dir"
        :style="ctl('90px')"
        :disabled="!state.primary_sort"
        @change="emit('search')"
      >
        <el-option label="降序" value="desc" />
        <el-option label="升序" value="asc" />
      </el-select>
      <span class="sep">+</span>
      <el-select
        v-model="state.secondary_sort"
        :style="ctl('130px')"
        :disabled="!state.primary_sort"
        @change="emit('search')"
      >
        <el-option label="无" value="" />
        <el-option label="活跃值" value="activity_score" />
        <el-option label="发布时间" value="publish_time" />
      </el-select>
      <el-select
        v-model="state.secondary_dir"
        :style="ctl('90px')"
        :disabled="!state.primary_sort"
        @change="emit('search')"
      >
        <el-option label="降序" value="desc" />
        <el-option label="升序" value="asc" />
      </el-select>
    </el-form-item>
    <el-form-item label="发布时间">
      <el-date-picker
        v-model="state.publishRange"
        type="daterange"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        :shortcuts="dateShortcuts"
        :style="ctl('240px')"
        @change="emit('search')"
      />
    </el-form-item>
    <el-form-item>
      <el-button type="primary" @click="emit('search')">查询</el-button>
      <el-button @click="emit('reset')">重置</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import type { JobFilterState } from '@/utils/jobFilterState'

const props = defineProps<{
  mode: 'inline' | 'stack'
  state: JobFilterState
  cityOptions: string[]
  districtOptions: string[]
}>()

const emit = defineEmits<{ search: []; reset: []; 'city-change': [] }>()

function ctl(desktopPx: string) {
  return props.mode === 'stack' ? { width: '100%' } : { width: desktopPx }
}

function daysAgo(n: number): Date {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d
}

const dateShortcuts: Array<{ text: string; value: () => [Date, Date] }> = [
  { text: '今天', value: () => [new Date(), new Date()] },
  { text: '近7天', value: () => [daysAgo(6), new Date()] },
  { text: '近30天', value: () => [daysAgo(29), new Date()] },
  { text: '近90天', value: () => [daysAgo(89), new Date()] },
]
</script>

<style scoped>
.sep { margin: 0 8px; color: var(--el-text-color-secondary); }
</style>
