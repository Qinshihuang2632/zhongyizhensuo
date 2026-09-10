import { createRouter, createWebHashHistory } from 'vue-router'
import { api, getToken } from './api'

import Setup from './views/Setup.vue'
import Login from './views/Login.vue'
import Home from './views/Home.vue'
import Settings from './views/Settings.vue'
import Patients from './views/Patients.vue'
import TreatmentRegister from './views/TreatmentRegister.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/login', component: Login },
    { path: '/setup', component: Setup },
    { path: '/settings', component: Settings },
    { path: '/patients', component: Patients },
    { path: '/treatment-register', component: TreatmentRegister },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  let status
  try {
    status = await api('/setup/status')
  } catch {
    return to.path === '/login' ? true : '/login'  // 服务异常时停在登录页提示
  }
  if (!status.initialized) return to.path === '/setup' ? true : '/setup'
  if (to.path === '/setup') return '/login'
  if (to.path === '/login') return getToken() ? '/' : true
  if (!getToken()) return '/login'
  return true
})
