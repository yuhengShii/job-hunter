<template>
  <div class="login-page">
    <el-card class="login-card">
      <template #header>
        <div class="login-title">Job Hunter 登录</div>
      </template>
      <el-form label-width="0" @submit.prevent>
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="submit">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function submit() {
  if (!form.username || !form.password) {
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/tasks')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}
.login-card { width: 360px; }
.login-title { text-align: center; font-size: 18px; }
.login-btn { width: 100%; }
</style>
