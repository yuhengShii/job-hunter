<template>
  <el-container class="layout">
    <el-aside v-if="!isMobile" width="200px">
      <el-menu :default-active="$route.path" router>
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
          <el-button v-if="isMobile" class="menu-btn" text @click="drawerVisible = true">
            <el-icon :size="20"><Menu /></el-icon>
          </el-button>
          <span class="page-title">{{ $route.meta.title }}</span>
        </div>
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
    <el-drawer v-if="isMobile" v-model="drawerVisible" direction="ltr" size="200px" :with-header="false">
      <el-menu :default-active="$route.path" router @select="drawerVisible = false">
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Menu, Odometer, Files, OfficeBuilding, DataAnalysis, Key, Promotion, ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const auth = useAuthStore()
const isMobile = useIsMobile()
const drawerVisible = ref(false)

const menuItems = [
  { path: '/tasks', icon: Odometer, label: '任务控制台' },
  { path: '/jobs', icon: Files, label: '职位列表' },
  { path: '/companies', icon: OfficeBuilding, label: '公司列表' },
  { path: '/stats', icon: DataAnalysis, label: '统计看板' },
  { path: '/credentials', icon: Key, label: '站点账号' },
  { path: '/apply', icon: Promotion, label: '一键投递' },
]

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
.header-left { display: flex; align-items: center; gap: 4px; }
.user-name { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
</style>
