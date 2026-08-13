<template>
  <div>
    <el-card class="filter-card">
      <el-form :inline="!isMobile">
        <el-form-item label="站点">
          <el-select v-model="query.site" clearable placeholder="全部站点" :style="inputStyle('160px')" @change="search">
            <el-option v-for="s in SITE_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="openCreate">新建账号</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <el-table :data="list" v-loading="loading">
        <el-table-column label="站点" width="110">
          <template #default="{ row }">{{ siteName(row.site) }}</template>
        </el-table-column>
        <el-table-column prop="username" label="账号" min-width="160" />
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">{{ row.remark ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="密码" width="90">
          <template #default="{ row }">{{ row.has_password ? '已设置' : '-' }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" :loading="testingId === row.id" @click="testLogin(row)">测试登录</el-button>
            <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog.visible" :title="dialog.editing ? '编辑账号' : '新建账号'" width="420px">
      <el-form label-width="80px">
        <el-form-item label="站点">
          <el-select v-model="dialog.site" style="width: 100%" :disabled="dialog.editing">
            <el-option v-for="s in SITE_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="dialog.username" :disabled="dialog.editing" placeholder="51job 登录手机号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="dialog.password"
            type="password"
            show-password
            :placeholder="dialog.editing ? '留空则不修改' : '请输入密码'"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dialog.remark" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { siteCredentialsApi, type SiteCredentialOut } from '@/api/siteCredentials'
import { formatTime } from '@/utils/format'
import { useIsMobile } from '@/composables/useIsMobile'

const SITE_OPTIONS = [
  { value: '51job', label: '51job' },
]

const loading = ref(false)
const saving = ref(false)
const testingId = ref<number | null>(null)
const list = ref<SiteCredentialOut[]>([])
const isMobile = useIsMobile()

const query = reactive({ site: '' })

const dialog = reactive({
  visible: false,
  editing: false,
  id: 0,
  site: '51job',
  username: '',
  password: '',
  remark: '',
})

function inputStyle(desktopPx: string) {
  return isMobile.value ? { width: '100%' } : { width: desktopPx }
}

function siteName(site: string): string {
  return SITE_OPTIONS.find((s) => s.value === site)?.label ?? site
}

async function load() {
  loading.value = true
  try {
    list.value = await siteCredentialsApi.list(query.site || undefined)
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function search() {
  load()
}

function openCreate() {
  dialog.editing = false
  dialog.id = 0
  dialog.site = '51job'
  dialog.username = ''
  dialog.password = ''
  dialog.remark = ''
  dialog.visible = true
}

function openEdit(row: SiteCredentialOut) {
  dialog.editing = true
  dialog.id = row.id
  dialog.site = row.site
  dialog.username = row.username
  dialog.password = ''
  dialog.remark = row.remark ?? ''
  dialog.visible = true
}

async function save() {
  if (!dialog.username.trim() || (!dialog.password && !dialog.editing)) {
    ElMessage.warning(dialog.editing ? '请输入账号' : '请输入账号和密码')
    return
  }
  saving.value = true
  try {
    if (dialog.editing) {
      await siteCredentialsApi.update(dialog.id, {
        remark: dialog.remark || null,
        password: dialog.password || null,
      })
    } else {
      await siteCredentialsApi.create({
        site: dialog.site,
        username: dialog.username.trim(),
        password: dialog.password,
        remark: dialog.remark || null,
      })
    }
    ElMessage.success('已保存')
    dialog.visible = false
    await load()
  } catch {
    // 拦截器已提示（409 重复）
  } finally {
    saving.value = false
  }
}

async function testLogin(row: SiteCredentialOut) {
  testingId.value = row.id
  try {
    const result = await siteCredentialsApi.testLogin(row.id)
    if (result.ok) {
      ElMessage.success(result.message)
    } else {
      ElMessage.error(result.message)
    }
  } catch {
    // 拦截器已提示
  } finally {
    testingId.value = null
  }
}

async function remove(row: SiteCredentialOut) {
  try {
    await ElMessageBox.confirm(`确认删除账号「${row.username}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await siteCredentialsApi.remove(row.id)
    await load()
  } catch {
    // 拦截器已提示（409 被引用）
  }
}

onMounted(load)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
</style>
