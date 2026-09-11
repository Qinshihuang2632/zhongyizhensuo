<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">收费结算</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <el-card>
        <template #header>
          <div class="list-head">
            <span>待收费单据（散户现结 / 住院单据在出院时统一结算）</span>
            <div style="display:flex;gap:12px;align-items:center">
              <el-select v-model="sourceFilter" style="width:150px" @change="loadPending">
                <el-option label="全部类型" value="" />
                <el-option label="治疗项目" value="treatment_order" />
                <el-option label="中药处方" value="prescription" />
                <el-option label="药品销售" value="sale" />
              </el-select>
              <el-input v-model="kw" placeholder="患者 / 单号" clearable style="width:180px"
                @keyup.enter="loadPending" @clear="loadPending">
                <template #append><el-button :icon="'Search'" @click="loadPending" /></template>
              </el-input>
            </div>
          </div>
        </template>
        <div v-if="selPending.length" class="merge-bar">
          <span>已选 <b>{{ selPending.length }}</b> 张单，合计 <b>¥ {{ selPendingTotal.toFixed(2) }}</b></span>
          <el-button size="small" type="primary" @click="settleBatch('现金')">合并收款（现金）</el-button>
          <el-button size="small" type="success" @click="settleBatch('扫码')">合并收款（扫码）</el-button>
          <span class="hint">同一患者的多张单可勾选后一并收总账，打印一张合并凭证</span>
        </div>
        <el-table :data="pending" v-loading="loading" size="small" border @selection-change="selPending = $event">
          <el-table-column type="selection" width="40" />
          <el-table-column label="单号" width="100">
            <template #default="{ row }">
              {{ { treatment_order: 'TO', prescription: 'CF', sale: 'XC' }[row._type] }}{{ String(row.id).padStart(6, '0') }}
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">{{ { treatment_order: '治疗', prescription: '处方', sale: '销售' }[row._type] }}</template>
          </el-table-column>
          <el-table-column prop="owner_type" label="对象" width="70" />
          <el-table-column prop="patient_name" label="患者" min-width="110" show-overflow-tooltip />
          <el-table-column label="金额" width="100">
            <template #default="{ row }">¥ {{ row.total.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="150" />
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <template v-if="row.owner_type === '散户'">
                <el-button size="small" type="primary" @click="settle(row, '现金')">现金收款</el-button>
                <el-button size="small" type="success" @click="settle(row, '扫码')">扫码到账</el-button>
              </template>
              <span v-else style="color:#b45309;font-size:12px">住院记账 · 出院时结算</span>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:12px;justify-content:flex-end" layout="total, prev, pager, next"
          :total="pendingTotal" :page-size="size" :current-page="page" @current-change="p => { page = p; loadPending() }" />
      </el-card>

      <el-card>
        <template #header>散户退费（退回已收费单据并恢复库存；可勾选多张一并退）</template>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <el-input v-model="refundKw" placeholder="搜索已收费单据：患者 / 单号" style="width:280px" @keyup.enter="searchRefundable" @clear="refundable = []" />
          <el-button :icon="'Search'" @click="searchRefundable">搜索</el-button>
        </div>
        <div v-if="selRefund.length" class="merge-bar">
          <span>已选 <b>{{ selRefund.length }}</b> 张单，合计 <b>¥ {{ selRefundTotal.toFixed(2) }}</b></span>
          <el-button size="small" type="danger" @click="refundBatch">合并退费</el-button>
        </div>
        <el-table v-if="refundable.length" :data="refundable" size="small" border style="margin-top:10px"
          @selection-change="selRefund = $event">
          <el-table-column type="selection" width="40" />
          <el-table-column label="单号" width="100">
            <template #default="{ row }">{{ { treatment_order: 'TO', prescription: 'CF', sale: 'XC' }[row._type] }}{{ String(row.id).padStart(6, '0') }}</template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">{{ { treatment_order: '治疗', prescription: '处方', sale: '销售' }[row._type] }}</template>
          </el-table-column>
          <el-table-column prop="patient_name" label="患者" min-width="110" />
          <el-table-column label="金额" width="100">
            <template #default="{ row }">¥ {{ row.total.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="150" />
          <el-table-column label="操作" width="110">
            <template #default="{ row }">
              <el-button size="small" type="danger" @click="refund(row)">退费</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card>
        <template #header>住院预交款</template>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <el-select v-model="admId" filterable placeholder="选择在院患者" style="width:280px">
            <el-option v-for="a in admissions" :key="a.id" :label="`${a.patient_name}（${a.no}）`" :value="a.id" />
          </el-select>
          <el-input-number v-model="depAmount" :min="0.01" :max="999999" :precision="2" placeholder="金额" style="width:160px" />
          <el-radio-group v-model="depMethod">
            <el-radio-button value="现金">现金</el-radio-button>
            <el-radio-button value="扫码">扫码</el-radio-button>
          </el-radio-group>
          <el-button type="primary" :loading="depSaving" @click="deposit">收取预交款</el-button>
        </div>
      </el-card>
    </main>

    <PrintPreview v-model:visible="printVisible" :html="printHtml" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import PrintPreview from '../components/PrintPreview.vue'

const pending = ref([])
const pendingTotal = ref(0)
const page = ref(1)
const size = 20
const sourceFilter = ref('')
const kw = ref('')
const loading = ref(false)
const selPending = ref([])
const selRefund = ref([])
const refundKw = ref('')
const refundable = ref([])
const admissions = ref([])
const admId = ref(null)
const depAmount = ref()
const depMethod = ref('现金')
const depSaving = ref(false)
const printVisible = ref(false)
const printHtml = ref('')

async function loadPending() {
  loading.value = true
  try {
    const items = []
    for (const [t, status] of [['treatment_order', '待收费'], ['prescription', '已付药'], ['sale', '待收费']]) {
      if (sourceFilter.value && sourceFilter.value !== t) continue
      const r = await api(`/${{ treatment_order: 'treatment-orders', prescription: 'prescriptions', sale: 'sales' }[t]}?status=${encodeURIComponent(status)}&keyword=${encodeURIComponent(kw.value)}&size=100`)
      r.items.forEach(i => items.push({ ...i, _type: t }))
    }
    items.sort((a, b) => b.id - a.id)
    pending.value = items
    pendingTotal.value = items.length
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

async function settle(row, method) {
  try {
    await ElMessageBox.confirm(`确认为 ${row.patient_name} 收款 ¥${row.total.toFixed(2)}（${method}）吗？`, '收费', { type: 'warning' })
  } catch { return }
  try {
    const r = await api('/charges/settle', { method: 'POST', body: { source_type: row._type, source_id: row.id, method } })
    ElMessage.success(`收费成功 ${r.no}`)
    await showChargeReceipt(r.id)
    loadPending()
  } catch (e) { ElMessage.error(e.message) }
}

const selPendingTotal = computed(() => selPending.value.reduce((s, r) => s + r.total, 0))
const selRefundTotal = computed(() => selRefund.value.reduce((s, r) => s + r.total, 0))

async function showChargeReceipt(chargeId) {
  const d = await api(`/charges/${chargeId}`)
  const { html } = await api('/print/preview', { method: 'POST', body: { template: 'charge', data: { c: d } } })
  printHtml.value = html
  printVisible.value = true
}

async function settleBatch(method) {
  if (!selPending.value.length) return
  try {
    await ElMessageBox.confirm(
      `确认为 ${selPending.value[0].patient_name} 合并收款 ¥${selPendingTotal.value.toFixed(2)}（${method}，共 ${selPending.value.length} 张单）吗？`,
      '合并收费', { type: 'warning' },
    )
  } catch { return }
  try {
    const r = await api('/charges/settle-batch', {
      method: 'POST',
      body: {
        method,
        items: selPending.value.map(x => ({ source_type: x._type, source_id: x.id })),
      },
    })
    ElMessage.success(`合并收费成功 ${r.no}，共 ¥${r.total ?? r.amount}`)
    await showChargeReceipt(r.id)
    selPending.value = []
    loadPending()
  } catch (e) { ElMessage.error(e.message) }
}

async function refundBatch() {
  if (!selRefund.value.length) return
  try {
    await ElMessageBox.confirm(
      `确定合并退费 ¥${selRefundTotal.value.toFixed(2)}（共 ${selRefund.value.length} 张单）吗？药品库存将退回。`,
      '合并退费', { type: 'warning' },
    )
  } catch { return }
  try {
    const r = await api('/charges/refund-batch', {
      method: 'POST',
      body: { items: selRefund.value.map(x => ({ source_type: x._type, source_id: x.id })) },
    })
    ElMessage.success(`合并退费成功 ${r.no}`)
    await showChargeReceipt(r.id)
    selRefund.value = []
    searchRefundable()
    loadPending()
  } catch (e) { ElMessage.error(e.message) }
}

async function searchRefundable() {
  try {
    const items = []
    for (const [t, status] of [['treatment_order', '已收费'], ['prescription', '已收费'], ['sale', '已收费']]) {
      const r = await api(`/${{ treatment_order: 'treatment-orders', prescription: 'prescriptions', sale: 'sales' }[t]}?status=${encodeURIComponent(status)}&keyword=${encodeURIComponent(refundKw.value)}&size=50`)
      r.items.forEach(i => items.push({ ...i, _type: t }))
    }
    items.sort((a, b) => b.id - a.id)
    refundable.value = items.slice(0, 50)
  } catch (e) { ElMessage.error(e.message) }
}

async function refund(row) {
  try {
    await ElMessageBox.confirm(`确定退费 ${row.patient_name} 的单据（¥${row.total.toFixed(2)}）吗？药品库存将退回。`, '退费', { type: 'warning' })
  } catch { return }
  try {
    await api('/charges/refund', { method: 'POST', body: { source_type: row._type, source_id: row.id } })
    ElMessage.success('退费完成')
    searchRefundable()
    loadPending()
  } catch (e) { ElMessage.error(e.message) }
}

async function deposit() {
  if (!admId.value || !depAmount.value) return ElMessage.warning('请选择在院患者并填写金额')
  depSaving.value = true
  try {
    await api('/charges/deposit', { method: 'POST', body: { admission_id: admId.value, amount: depAmount.value, method: depMethod.value } })
    ElMessage.success('预交款已登记')
    depAmount.value = undefined
  } catch (e) { ElMessage.error(e.message) } finally { depSaving.value = false }
}

onMounted(async () => {
  loadPending()
  try {
    const r = await api('/admissions?status=' + encodeURIComponent('在院'))
    admissions.value = r.items
  } catch { /* 忽略 */ }
})
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; display: flex; flex-direction: column; gap: 20px; }
.list-head { display: flex; justify-content: space-between; align-items: center; }
.merge-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; padding: 8px 12px; background: #ecf5ff; border-radius: 6px; font-size: 14px; }
.merge-bar .hint { color: #888; font-size: 12px; }
</style>
