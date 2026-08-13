import { createRouter, createWebHistory } from 'vue-router'
import { TOKEN_KEY } from '@/api/http'
import Layout from '@/components/Layout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/Login.vue') },
    {
      path: '/',
      component: Layout,
      children: [
        { path: '', redirect: '/tasks' },
        { path: 'tasks', component: () => import('@/views/Tasks.vue'), meta: { title: '任务控制台' } },
        { path: 'jobs', component: () => import('@/views/Jobs.vue'), meta: { title: '职位列表' } },
        { path: 'companies', component: () => import('@/views/Companies.vue'), meta: { title: '公司列表' } },
        { path: 'stats', component: () => import('@/views/Stats.vue'), meta: { title: '统计看板' } },
        { path: 'credentials', component: () => import('@/views/SiteCredentials.vue'), meta: { title: '站点账号' } },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const authed = !!localStorage.getItem(TOKEN_KEY)
  if (to.path !== '/login' && !authed) return '/login'
  if (to.path === '/login' && authed) return '/tasks'
  return true
})

export default router
