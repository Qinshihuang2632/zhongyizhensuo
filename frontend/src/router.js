import { createRouter, createWebHashHistory } from 'vue-router'
import { api, getToken } from './api'

import Setup from './views/Setup.vue'
import Login from './views/Login.vue'
import Home from './views/Home.vue'
import Settings from './views/Settings.vue'
import Patients from './views/Patients.vue'
import TreatmentRegister from './views/TreatmentRegister.vue'
import Prescriptions from './views/Prescriptions.vue'
import Sales from './views/Sales.vue'
import Charge from './views/Charge.vue'
import Discharge from './views/Discharge.vue'
import PrintCenter from './views/PrintCenter.vue'
import QueryCenter from './views/QueryCenter.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/login', component: Login },
    { path: '/setup', component: Setup },
    { path: '/settings', component: Settings },
    { path: '/patients', component: Patients },
    { path: '/treatment-register', component: TreatmentRegister },
    { path: '/prescriptions', component: Prescriptions },
    { path: '/sales', component: Sales },
    { path: '/charge', component: Charge },
    { path: '/discharge', component: Discharge },
    { path: '/print-center', component: PrintCenter },
    { path: '/query-center', component: QueryCenter },
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
