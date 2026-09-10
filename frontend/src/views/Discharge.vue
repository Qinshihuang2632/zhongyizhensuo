<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">办理出院</span>
      <span style="width:76px"></span>
    </header>

    <main class="content" v-if="!current">
      <el-card>
        <template #header>
          <div class="list-head">
            <span>在院患者</span>
            <el-input v-model="kw" placeholder="患者 / 住院号" clearable style="width:200px"
              @keyup.enter="load" @clear="load">
              <template #append><el-button :icon="'Search'" @click="load" /></template>
            </el-input>
          </div>
        </template>
        <el-table :data="list" v-loading="loading" size="small" border>
          <el-table-column prop="no" label="住院号" width="90" />
          <el-table-column prop="patient_name" label="患者" min-width="110" />
          <el-table-column prop="admitted_at" label="入院时间" width="160" />
          <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip />
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="openOne(row)">选择并查看费用</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:12px;justify-content:flex-end" layout="total, prev, pager, next"
          :total="total" :page-size="size" :current-page="page" @current-change="p => { page = p; load() }" />
      </el-card>

      <el-card>
        <template #header>住院登记（新患者入院）</template>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <el-select v-model="newPid" filterable remote clearable :remote-method="searchPatients"
            :loading="searching" placeholder="从患者档案选择" style="width:280px">
            <el-option v-for="p in patientOptions" :key="p.id" :label="`${p.name}（${p.no}，${p.phone}）`" :value="p.id" />
          </el-select>
          <el-input v-model="newNote" placeholder="备注（选填）" style="width:240px" maxlength="200" />
          <el-button type="primary" :loading="saving" @click="admit">办理入院</el-button>
        </div>
      </el-card>
    </main>

    <main class="content" v-else>
      <el-card>
        <template #header>
          <div class="list-head">
            <span>住院详情 · {{ current.no }} · {{ current.patient_name }}</span>
            <el-button :icon="'Back'" @click="current = null; load()">返回列表</el-button>
          </div>
        </template>
        <div class="summary">
          <div><span class="k">入院时间</span><b>{{ current.admitted_at }}</b></div>
          <div><span class="k">预交款合计</span><b>¥ {{ current.deposits.toFixed(2) }}</b></div>
          <div><span class="k">已入账费用</span><b>¥ {{ current.billed.toFixed(2) }}</b></div>
          <div><span class="k">待收费单据</span><b>¥ {{ current.pending.toFixed(2) }}</b></div>
          <div><span class="k">预估结余（应补收）</span><b :style="{ color: current.balance > 0 ? '#c0392b' : '#0a7d43' }">¥ {{ current.balance.toFixed(2) }}</b></div>
        </div>

        <el-tabs style="margin-top:10px">
          <el-tab-pane label="治疗项目">
            <el-table :data="current.treatments" size="small" border>
              <el-table-column label="单号" width="100"><template #default="{ row }">TO{{ String(row.id).padStart(6, '0') }}</template></el-table-column>
              <el-table-column prop="created_at" label="时间" width="160" />
              <el-table-column prop="status" label="状态" width="90" />
              <el-table-column label="金额" width="100"><template #default="{ row }">¥ {{ row.total.toFixed(2) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="成药销售">
            <el-table :data="current.sales" size="small" border>
              <el-table-column label="单号" width="100"><template #default="{ row }">XC{{ String(row.id).padStart(6, '0') }}</template></el-table-column>
              <el-table-column prop="created_at" label="时间" width="160" />
              <el-table-column prop="status" label="状态" width="90" />
              <el-table-column label="金额" width="100"><template #default="{ row }">¥ {{ row.total.toFixed(2) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="中药处方">
            <el-table :data="current.prescriptions" size="small" border>
              <el-table-column label="单号" width="100"><template #default="{ row }">CF{{ String(row.id).padStart(6, '0') }}</template></el-table-column>
              <el-table-column prop="created_at" label="时间" width="160" />
              <el-table-column prop="status" label="状态" width="90" />
              <el-table-column label="金额" width="100"><template #default="{ row }">¥ {{ row.total.toFixed(2) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>

        <div style="margin-top:16px;display:flex;gap:16px;align-items:center">
          <el-radio-group v-model="method">
            <el-radio-button value="现金">补收-现金</el-radio-button>
            <el-radio-button value="扫码">补收-扫码</el-radio-button>
          </el-radio-group>
          <el-button type="danger" :loading="discharging" @click="discharge">结算并办理出院</el-button>
        </div>
        <p class="hint">出院将把全部待收费单据统一收费，与预交款对冲：差额补收、多缴退回，随后可打印《出院汇总清单》（含出院医嘱）。请先确认处方都已付药。</p>
      </el-card>
    </main>

    <PrintPreview v-model:visible="printVisible" :html="printHtml" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import PrintPreview from '../components/PrintPreview.vue'

const list = ref([])
const total = ref(0)
const page = ref(1)
const size = 20
const kw = ref('')
const loading = ref(false)
const current = ref(null)
const method = ref('现金')
const discharging = ref(false)
const printVisible = ref(false)
const printHtml = ref('')
const newPid = ref(null)
const newNote = ref('')
const saving = ref(false)
const patientOptions = ref([])
const searching = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api(`/admissions?status=${encodeURIComponent('在院')}&keyword=${encodeURIComponent(kw.value)}&page=${page.value}&size=${size}`)
    list.value = r.items
    total.value = r.total
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

async function searchPatients(q) {
  if (!q) { patientOptions.value = []; return }
  searching.value = true
  try {
    patientOptions.value = (await api(`/patients?keyword=${encodeURIComponent(q)}&size=20`)).items
  } catch { /* 忽略 */ } finally { searching.value = false }
}

async function admit() {
  if (!newPid.value) return ElMessage.warning('请从患者档案选择患者')
  saving.value = true
  try {
    const r = await api('/admissions', { method: 'POST', body: { patient_id: newPid.value, note: newNote.value } })
    ElMessage.success(`入院登记成功：${r.no}。预交款请到「收费结算」收取。`)
    newPid.value = null; newNote.value = ''
    load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function openOne(row) {
  try {
    current.value = await api(`/admissions/${row.id}`)
  } catch (e) { ElMessage.error(e.message) }
}

async function discharge() {
  try {
    await ElMessageBox.confirm(
      `确定为 ${current.value.patient_name} 办理出院吗？将统一结算全部费用并与预交款对冲。`,
      '出院结算', { type: 'warning', confirmButtonText: '结算并出院', cancelButtonText: '取消' },
    )
  } catch { return }
  discharging.value = true
  try {
    const r = await api(`/admissions/${current.value.id}/discharge`, { method: 'POST', body: { method: method.value } })
    ElMessage.success(`出院完成，${r.balance >= 0 ? '补收' : '退回'} ¥${Math.abs(r.balance).toFixed(2)}`)
    const d = await api(`/admissions/${current.value.id}`)
    d.balance = r.balance
    const { html } = await api('/print/preview', { method: 'POST', body: { template: 'discharge', data: d } })
    printHtml.value = html
    printVisible.value = true
    current.value = null
    load()
  } catch (e) { ElMessage.error(e.message) } finally { discharging.value = false }
}

onMounted(load)
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; display: flex; flex-direction: column; gap: 20px; }
.list-head { display: flex; justify-content: space-between; align-items: center; }
.summary { display: flex; gap: 28px; flex-wrap: wrap; font-size: 14px; }
.summary .k { color: #888; margin-right: 6px; }
.hint { color: #b45309; font-size: 13px; margin-top: 10px; }
</style>
