<template>
  <div class="page">
    <header class="topbar">
      <div class="brand">
        <span class="clinic">{{ clinicName || '中医诊所管理系统' }}</span>
        <span class="sub">管理端 v{{ version }}</span>
      </div>
      <div class="actions">
        <el-button :icon="'Setting'" @click="$router.push('/settings')">系统设置</el-button>
        <el-button type="danger" plain :icon="'SwitchButton'" @click="shutdown">退出系统</el-button>
      </div>
    </header>

    <el-alert
      v-if="backupWarn"
      type="warning"
      :closable="false"
      show-icon
      style="margin: 12px 24px 0"
      :title="backupWarn"
    />

    <main class="content">
      <div class="tiles">
        <button
          v-for="m in modules"
          :key="m.key"
          class="tile"
          :class="{ enabled: m.enabled }"
          :disabled="!m.enabled"
          @click="m.enabled && $router.push(m.to)"
        >
          <el-icon :size="34"><component :is="m.icon" /></el-icon>
          <span>{{ m.label }}</span>
        </button>
      </div>

      <el-card class="status">
        <template #header>系统状态</template>
        <div class="rows">
          <div><span class="k">程序版本</span><span>{{ version }}</span></div>
          <div><span class="k">数据目录</span><span class="mono">{{ dataDir }}</span></div>
          <div><span class="k">最近自动备份</span><span>{{ lastAutoBackup || '尚无（将在下次启动时自动备份）' }}</span></div>
          <div><span class="k">备份保留份数</span><span>{{ backupKeep }} 份</span></div>
        </div>
      </el-card>
    </main>

    <div v-if="exited" class="exited">系统已退出，如窗口未自动关闭请手动关闭本窗口。</div>

    <!-- 保健卡权益提醒：确认前每次登录都会弹出（跨重启） -->
    <el-dialog
      v-model="cardRemindVisible"
      title="保健卡权益提醒"
      width="560px"
      top="6vh"
      :close-on-click-modal="false"
    >
      <div v-if="cardReminders.length" class="remind-wrap">
        <div class="remind-summary" @click="remindExpanded = !remindExpanded">
          <el-icon :size="16"><Bell /></el-icon>
          <span>共 <b>{{ cardReminders.length }}</b> 位患者的保健卡权益需要提醒
          <span class="fold-tip">（点击{{ remindExpanded ? '收起' : '展开' }}）</span></span>
        </div>
        <div v-show="remindExpanded" class="remind-list">
          <div v-for="r in cardReminders" :key="r.patient_id + '-' + r.window_index" class="remind-item">
            <div class="line1">
              <b>{{ r.patient_name }}</b>
              <span class="phone">电话：{{ r.phone || '—' }}</span>
            </div>
            <div class="line2">
              权益时间：{{ r.start }} ~ {{ r.end }}
              <el-tag size="small" :type="r.effective ? 'warning' : 'info'">
                {{ r.effective ? '已生效，请尽快安排来店' : `${r.days_to_start} 天后生效` }}
              </el-tag>
            </div>
            <div class="line3">
              <el-button size="small" type="primary" @click="confirmRemind(r)">确认已提醒患者</el-button>
            </div>
          </div>
        </div>
        <div class="remind-tip">确认前，每次登录系统都会持续提醒；关闭系统不会丢失提醒。</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const clinicName = ref('')
const version = ref('')
const dataDir = ref('')
const lastAutoBackup = ref('')
const backupKeep = ref(30)
const exited = ref(false)

const modules = [
  { key: 'reg', label: '患者信息', icon: 'User', to: '/patients', enabled: true },
  { key: 'item', label: '项目登记', icon: 'List', to: '/treatment-register', enabled: true },
  { key: 'sale', label: '药品销售', icon: 'ShoppingCart', to: '/sales', enabled: true },
  { key: 'rx', label: '处方开药', icon: 'EditPen', to: '/prescriptions', enabled: true },
  { key: 'disch', label: '住院手续', icon: 'Finished', to: '/discharge', enabled: true },
  { key: 'charge', label: '收费结算', icon: 'Money', to: '/charge', enabled: true },
  { key: 'print', label: '打印中心', icon: 'Printer', to: '/print-center', enabled: true },
  { key: 'query', label: '查询中心', icon: 'Search', to: '/query-center', enabled: true },
]

const backupWarn = computed(() => {
  if (!lastAutoBackup.value) return '还没有自动备份：重启一次程序即可完成今日备份，或到「系统设置 → 备份管理」手动备份。'
  return ''
})

onMounted(async () => {
  const health = await api('/health')
  version.value = health.version
  dataDir.value = health.data_dir
  const s = await api('/setup/status')
  clinicName.value = s.clinic_name
  const cfg = await api('/settings')
  lastAutoBackup.value = cfg.last_auto_backup || ''
  backupKeep.value = cfg.backup_keep || 30
  loadCardReminders()
})

const cardReminders = ref([])
const cardRemindVisible = ref(false)
const remindExpanded = ref(true)

async function loadCardReminders() {
  try {
    cardReminders.value = await api('/cards/reminders')
    if (cardReminders.value.length) {
      cardRemindVisible.value = true
      remindExpanded.value = cardReminders.value.length <= 3
    }
  } catch { /* 提醒加载失败不阻塞主界面 */ }
}

async function confirmRemind(r) {
  try {
    await api(`/cards/${r.patient_id}/reminders/${r.window_index}/confirm`, { method: 'POST' })
    cardReminders.value = cardReminders.value.filter(x => x !== r)
    if (!cardReminders.value.length) cardRemindVisible.value = false
    ElMessage.success('已记录提醒')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function shutdown() {
  try {
    await ElMessageBox.confirm('确定退出系统吗？', '退出', { type: 'warning', confirmButtonText: '退出', cancelButtonText: '取消' })
  } catch { return }
  try {
    await api('/shutdown', { method: 'POST' })
  } catch { /* 服务已停，忽略 */ }
  exited.value = true
  ElMessage.success('已退出')
  // 独立应用窗口（Edge/Chrome 应用模式）下尝试自动关闭窗口；失败则停留在退出提示页
  setTimeout(() => { try { window.close(); } catch { /* 忽略 */ } }, 600)
}
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }
.brand .clinic { font-size: 20px; font-weight: bold; margin-right: 12px; }
.brand .sub { opacity: .8; font-size: 13px; }
.content { padding: 24px; flex: 1; }
.tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.tile { height: 110px; border: 1px solid #e4e7ed; border-radius: 12px; background: #fff; display: flex; flex-direction: column; gap: 10px; align-items: center; justify-content: center; font-size: 16px; color: #9ca3af; cursor: not-allowed; }
.tile.enabled { color: #075e54; cursor: pointer; transition: all .15s; }
.tile.enabled:hover { box-shadow: 0 4px 16px rgba(7,94,84,.18); transform: translateY(-2px); }
.status .rows { display: grid; gap: 10px; font-size: 14px; }
.status .k { display: inline-block; width: 120px; color: #888; }
.mono { font-family: Consolas, monospace; word-break: break-all; }
.exited { position: fixed; inset: 0; background: rgba(0,0,0,.72); color: #fff; font-size: 22px; display: flex; align-items: center; justify-content: center; }
.remind-wrap { font-size: 14px; }
.remind-summary { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #fdf6ec; border: 1px solid #f5dab1; border-radius: 6px; cursor: pointer; }
.fold-tip { color: #909399; font-size: 12px; }
.remind-list { margin-top: 10px; max-height: 44vh; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.remind-item { border: 1px solid #ebeef5; border-radius: 8px; padding: 10px 12px; }
.remind-item .line1 { display: flex; justify-content: space-between; margin-bottom: 4px; }
.remind-item .phone { color: #666; }
.remind-item .line2 { color: #555; margin-bottom: 8px; }
.remind-item .line3 { text-align: right; }
.remind-tip { margin-top: 10px; color: #909399; font-size: 12px; }
</style>
