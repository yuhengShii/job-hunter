<template>
  <el-dialog
    :model-value="modelValue"
    title="一键批量投简历"
    width="440px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-form label-width="90px">
      <el-form-item label="登录账号">
        <el-select v-model="credentialId" placeholder="选择 51job 登录账号" style="width: 100%">
          <el-option
            v-for="c in credentials"
            :key="c.id"
            :label="`${c.site} · ${c.username}`"
            :value="c.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="投递范围">
        <el-radio-group v-model="scope">
          <el-radio value="favorites">全部收藏（{{ favoriteCount }} 条）</el-radio>
          <el-radio value="selected" :disabled="selectedCount === 0">仅选中（{{ selectedCount }} 条）</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">开始投递</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { SiteCredentialOut } from '@/api/siteCredentials'

const props = defineProps<{
  modelValue: boolean
  credentials: SiteCredentialOut[]
  favoriteCount: number
  selectedCount: number
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  create: [{ credential_id: number; scope: 'favorites' | 'selected' }]
}>()

const credentialId = ref<number | null>(null)
const scope = ref<'favorites' | 'selected'>('favorites')
const submitting = ref(false)

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      credentialId.value = props.credentials[0]?.id ?? null
      scope.value = props.selectedCount > 0 ? 'selected' : 'favorites'
      submitting.value = false
    }
  },
)

function submit() {
  if (credentialId.value == null) {
    ElMessage.warning('请选择登录账号')
    return
  }
  submitting.value = true
  emit('create', { credential_id: credentialId.value, scope: scope.value })
}
</script>
