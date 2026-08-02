<template>
  <el-container class="layout">
    <el-aside width="200px">
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/tasks"><el-icon><Odometer /></el-icon><span>任务控制台</span></el-menu-item>
        <el-menu-item index="/jobs"><el-icon><Files /></el-icon><span>职位列表</span></el-menu-item>
        <el-menu-item index="/companies"><el-icon><OfficeBuilding /></el-icon><span>公司列表</span></el-menu-item>
        <el-menu-item index="/stats"><el-icon><DataAnalysis /></el-icon><span>统计看板</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="layout-header">
        <span class="page-title">{{ $route.meta.title }}</span>
        <el-dropdown @command="onCommand">
          <span class="user-name">{{ auth.username }}<el-icon><ArrowDown /></el-icon></span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout { min-height: 100vh; }
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-light);
}
.user-name { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
</style>
