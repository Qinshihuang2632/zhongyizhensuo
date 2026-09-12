<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">系统设置</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <el-tabs>
        <el-tab-pane label="诊所信息">
          <el-form label-width="100px" style="max-width:560px">
            <el-form-item label="诊所名称"><el-input v-model="form.clinic_name" /></el-form-item>
            <el-form-item label="地址"><el-input v-model="form.clinic_address" /></el-form-item>
            <el-form-item label="电话"><el-input v-model="form.clinic_phone" /></el-form-item>
            <el-button type="primary" :loading="saving" @click="saveInfo">保存</el-button>
            <p class="hint">以上信息将出现在所有 A4 单据的抬头上。</p>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="字典管理" lazy>
          <Dictionary />
        </el-tab-pane>

        <el-tab-pane label="药库管理" lazy>
          <StockManager />
        </el-tab-pane>

        <el-tab-pane label="备份管理">
          <div class="bar">
            <el-button type="primary" :icon="'Plus'" :loading="backingUp" @click="createBackup">立即备份</el-button>
            <span class="keep">
              自动备份保留
              <el-input-number v-model="keepInput" :min="1" :max="365" size="small" />
              份
              <el-button size="small" @click="saveKeep">保存</el-button>
            </span>
          </div>
          <p class="hint">每天首次启动自动备份一次；「自动」备份超出保留份数后自动清理，「手动」备份永久保留。</p>
          <el-table :data="backups" size="small" max-height="300">
            <el-table-column prop="name" label="备份文件" min-width="240" />
            <el-table-column label="类型" width="80">
              <template #default="{ row }">
                <el-tag :type="row.kind === 'auto' ? 'info' : 'success'" size="small">
                  {{ row.kind === 'auto' ? '自动' : '手动' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="mtime" label="时间" width="140" />
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ (row.size / 1024).toFixed(0) }} KB</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" type="warning" plain @click="restore(row)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="mig">
            <div class="mig-title">数据迁移（换电脑）</div>
            <p class="hint">
              换电脑三步：①在旧电脑点「导出数据包」得到 zip；②把安装包拷到新电脑安装；
              ③新电脑点「导入数据包」并选择该 zip。导入前会自动备份当前数据，重启后生效。
            </p>
            <el-button type="primary" plain :icon="'Download'" :loading="exporting" @click="exportData">导出数据包</el-button>
            <el-button plain :icon="'Upload'" @click="importInput?.click()">导入数据包</el-button>
            <input ref="importInput" type="file" accept=".zip" style="display:none" @change="doImport" />
          </div>
        </el-tab-pane>

        <el-tab-pane label="软件更新">
          <div style="max-width:620px">
            <p style="margin-top:0">当前版本：<b>v{{ version }}</b></p>
            <p class="hint">
              更新方式：收到新版更新包（zip 文件，微信传输或下载均可）后，点下方按钮选择该文件。
              系统会自动校验并暂存，之后<b>退出系统并重新打开</b>即完成更新，数据不受影响。
            </p>
            <el-button type="primary" :icon="'Upload'" :loading="updating" @click="updateInput?.click()">
              选择更新包并准备更新
            </el-button>
            <input ref="updateInput" type="file" accept=".zip" style="display:none" @change="doUpdate" />
            <p v-if="updateReady" class="ready">✔ {{ updateReady }} 请退出系统并重新打开。</p>
          </div>
        </el-tab-pane>

        <el-tab-pane label="修改密码">          <el-form label-width="100px" style="max-width:480px">
            <el-form-item label="原密码"><el-input v-model="pwd.old" type="password" show-password /></el-form-item>
            <el-form-item label="新密码"><el-input v-model="pwd.new1" type="password" show-password placeholder="至少 6 位" /></el-form-item>
            <el-form-item label="确认新密码"><el-input v-model="pwd.new2" type="password" show-password /></el-form-item>
            <el-button type="primary" @click="changePwd">修改密码</el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="打印测试">
          <p class="hint" style="margin-top:0">
            M1 交付的 A4 打印框架：点「预览测试单」查看制式单据（抬头取自诊所信息），确认版式后可直接打印。
            后续里程碑的真实单据（患者信息表、处方笺、销售单等）将复用同一框架。
          </p>
          <el-button type="primary" :icon="'Printer'" @click="previewTest">预览测试单</el-button>
        </el-tab-pane>

        <el-tab-pane label="出院医嘱">
          <p class="hint" style="margin-top:0">
            出院汇总清单末尾会固定打印以下医嘱文字（即你要求的"固化医嘱"）。可一次性修改为本诊所的说法。
          </p>
          <el-input v-model="dischargeOrders" type="textarea" :rows="6" style="max-width:560px" />
          <div style="margin-top:10px">
            <el-button type="primary" @click="saveDischargeOrders">保存医嘱文案</el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="操作留痕" lazy>
          <el-table :data="auditItems" size="small" border max-height="430">
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column prop="action" label="动作" width="110" />
            <el-table-column prop="detail" label="内容" min-width="300" show-overflow-tooltip />
          </el-table>
          <el-pagination style="margin-top:12px;justify-content:flex-end" layout="total, prev, pager, next"
            :total="auditTotal" :page-size="auditSize" :current-page="auditPage"
            @current-change="p => { auditPage = p; loadAudit() }" />
        </el-tab-pane>
        <el-tab-pane label="关于">
          <div class="rows">
            <div><span class="k">系统</span><span>中医诊所管理系统 v{{ version }}</span></div>
            <div><span class="k">数据目录</span><span class="mono">{{ dataDir }}</span></div>
            <div><span class="k">换电脑</span><span>整个程序文件夹（含「数据」）拷到新电脑即可，或使用数据导出/导入（M8 提供）</span></div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </main>

    <PrintPreview v-model:visible="printVisible" :html="printHtml" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, getToken } from '../api'
import PrintPreview from '../components/PrintPreview.vue'
import Dictionary from '../components/Dictionary.vue'
import StockManager from '../components/StockManager.vue'

const form = ref({ clinic_name: '', clinic_address: '', clinic_phone: '' })
const backups = ref([])
const keepInput = ref(30)
const pwd = ref({ old: '', new1: '', new2: '' })
const version = ref('')
const dataDir = ref('')
const saving = ref(false)
const backingUp = ref(false)
const printVisible = ref(false)
const printHtml = ref('')
const dischargeOrders = ref('')
const auditItems = ref([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditSize = 50
const exporting = ref(false)
const updating = ref(false)
const updateReady = ref('')
const importInput = ref(null)
const updateInput = ref(null)

async function uploadRaw(path, file) {
  const res = await fetch('/api' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream', 'X-Token': getToken() },
    body: await file.arrayBuffer(),
  })
  const data = await res.json().catch(() => ({}))
  if (res.status === 401) {
    localStorage.removeItem('zyzs_token')
    location.hash = '#/login'
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) throw new Error(data.detail || `请求失败（${res.status}）`)
  return data
}

async function exportData() {
  exporting.value = true
  try {
    const res = await fetch('/api/migration/export', { headers: { 'X-Token': getToken() } })
    if (!res.ok) throw new Error('导出失败（' + res.status + '）')
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `数据包_${new Date().toISOString().slice(0, 10)}.zip`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('数据包已导出，请保存到 U 盘或微信发送到新电脑')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    exporting.value = false
  }
}

async function doImport(ev) {
  const file = ev.target.files?.[0]
  ev.target.value = ''
  if (!file) return
  try {
    await ElMessageBox.confirm(
      `确定导入「${file.name}」吗？导入前会自动备份当前数据；确认后程序将退出，重新打开即使用导入的数据。`,
      '导入数据包', { type: 'warning', confirmButtonText: '导入并退出', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await uploadRaw('/migration/import', file)
    ElMessage.success('导入已安排，程序即将退出…')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function doUpdate(ev) {
  const file = ev.target.files?.[0]
  ev.target.value = ''
  if (!file) return
  updating.value = true
  try {
    const r = await uploadRaw('/update/upload', file)
    updateReady.value = r.message
    ElMessage.success(`更新包已就绪（v${r.version}）`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    updating.value = false
  }
}

async function loadAll() {
  const health = await api('/health')
  version.value = health.version
  dataDir.value = health.data_dir
  const cfg = await api('/settings')
  form.value = {
    clinic_name: cfg.clinic_name || '',
    clinic_address: cfg.clinic_address || '',
    clinic_phone: cfg.clinic_phone || '',
  }
  keepInput.value = parseInt(cfg.backup_keep || '30', 10)
  dischargeOrders.value = cfg.discharge_orders || ''
  backups.value = await api('/backup/list')
}

function loadAudit() {
  api(`/audit?page=${auditPage.value}&size=${auditSize}`)
    .then(r => { auditItems.value = r.items; auditTotal.value = r.total })
    .catch(() => {})
}

async function saveDischargeOrders() {
  try {
    await api('/settings', { method: 'PUT', body: { values: { discharge_orders: dischargeOrders.value } } })
    ElMessage.success('医嘱文案已保存')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(loadAll)

async function saveInfo() {
  saving.value = true
  try {
    await api('/settings', { method: 'PUT', body: { values: { ...form.value } } })
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function saveKeep() {
  await api('/settings', { method: 'PUT', body: { values: { backup_keep: String(keepInput.value) } } })
  ElMessage.success('已保存')
}

async function createBackup() {
  backingUp.value = true
  try {
    const { name } = await api('/backup/create', { method: 'POST' })
    ElMessage.success('备份完成：' + name)
    backups.value = await api('/backup/list')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    backingUp.value = false
  }
}

async function restore(row) {
  try {
    await ElMessageBox.confirm(
      `确定用「${row.name}」恢复数据吗？恢复前会自动备份当前数据；` +
      '确认后程序将退出，重新启动程序即完成恢复。',
      '恢复数据', { type: 'warning', confirmButtonText: '恢复并退出', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await api('/backup/restore', { method: 'POST', body: { name: row.name } })
  } catch (e) {
    ElMessage.error(e.message)
    return
  }
  ElMessage.success('恢复已安排，程序即将退出…')
}

async function changePwd() {
  if (pwd.value.new1.length < 6) return ElMessage.warning('新密码至少 6 位')
  if (pwd.value.new1 !== pwd.value.new2) return ElMessage.warning('两次输入的新密码不一致')
  try {
    await api('/auth/change-password', {
      method: 'POST',
      body: { old_password: pwd.value.old, new_password: pwd.value.new1 },
    })
    ElMessage.success('密码已修改')
    pwd.value = { old: '', new1: '', new2: '' }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function previewTest() {
  const { html } = await api('/print/preview', { method: 'POST', body: { template: 'test_sheet', data: {} } })
  printHtml.value = html
  printVisible.value = true
}
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; }
.hint { color: #888; font-size: 13px; }
.bar { display: flex; align-items: center; gap: 20px; margin-bottom: 8px; }
.keep { color: #555; font-size: 14px; display: inline-flex; align-items: center; gap: 6px; }
.rows { display: grid; gap: 10px; font-size: 14px; }
.rows .k { display: inline-block; width: 90px; color: #888; }
.mono { font-family: Consolas, monospace; word-break: break-all; }
.mig { margin-top: 18px; padding: 12px 14px; background: #f8f9fa; border-radius: 8px; }
.mig-title { font-weight: bold; margin-bottom: 6px; }
.ready { color: #0a7d43; font-size: 14px; }
</style>
