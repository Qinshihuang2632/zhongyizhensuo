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
          <el-table :data="backups" size="small" max-height="420">
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
        </el-tab-pane>

        <el-tab-pane label="修改密码">
          <el-form label-width="100px" style="max-width:480px">
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
import { api } from '../api'
import PrintPreview from '../components/PrintPreview.vue'

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
  backups.value = await api('/backup/list')
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
</style>
