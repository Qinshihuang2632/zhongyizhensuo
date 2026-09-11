<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">处方开药 · 中药处方</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <el-card>
        <template #header>开新处方</template>
        <el-form label-width="90px">
          <el-row :gutter="12">
            <el-col :span="8">
              <el-form-item label="对象类型">
                <el-radio-group v-model="form.owner_type" @change="onOwnerChange">
                  <el-radio-button value="散户">散户</el-radio-button>
                  <el-radio-button value="住院">住院</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="16">
              <el-form-item label="患者" :required="form.owner_type === '住院'">
                <el-select v-model="form.patient_id" filterable remote clearable :remote-method="searchPatients"
                  :loading="searching" :placeholder="form.owner_type === '住院' ? '选择在院患者（可输入姓名过滤）' : '输入姓名 / 电话搜索患者档案'"
                  style="width:100%">
                  <el-option v-for="p in patientOptions" :key="p.id" :label="p.label" :value="p.id" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="12">
            <el-col :span="8">
              <el-form-item label="剂数" required>
                <el-input-number v-model="form.doses" :min="1" :max="1000" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="16">
              <el-form-item label="用法">
                <el-input v-model="form.usage_method" placeholder="如：水煎服，每日一剂，早晚分服" maxlength="100" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="药材">
            <div style="width:100%">
              <el-table :data="form.lines" size="small" border>
                <el-table-column label="饮片" min-width="220">
                  <template #default="{ row }">
                    <ItemSelect v-model="row.item_id" :categories="['中药饮片']" @change="it => onItem(row, it)" />
                  </template>
                </el-table-column>
                <el-table-column label="单价" width="90">
                  <template #default="{ row }">{{ (row.price || 0).toFixed(2) }}/{{ row.unit || '克' }}</template>
                </el-table-column>
                <el-table-column label="每剂用量" width="150">
                  <template #default="{ row }">
                    <el-input-number v-model="row.qty" :min="0.1" :max="9999" :step="1" size="small" style="width:100%" />
                  </template>
                </el-table-column>
                <el-table-column label="每剂金额" width="100">
                  <template #default="{ row }">{{ ((row.price || 0) * (row.qty || 0)).toFixed(2) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="70">
                  <template #default="{ $index }">
                    <el-button size="small" type="danger" plain :icon="'Delete'" @click="form.lines.splice($index, 1)" />
                  </template>
                </el-table-column>
              </el-table>
              <div style="margin-top:8px;display:flex;align-items:center;gap:16px">
                <el-button size="small" type="primary" plain :icon="'Plus'" @click="form.lines.push({ item_id: null, qty: 1, price: 0, unit: '克' })">加一味</el-button>
                <span>每剂：<b>¥ {{ perDose.toFixed(2) }}</b></span>
                <span class="total">合计（×{{ form.doses }}剂）：<b>¥ {{ total.toFixed(2) }}</b></span>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="form.note" maxlength="200" style="width:420px" /></el-form-item>
          <div class="actions">
            <el-button type="primary" :loading="saving" @click="save">保存处方（待付药）</el-button>
            <el-button v-if="editingId" @click="cancelEdit">取消修改</el-button>
          </div>
        </el-form>
      </el-card>

      <el-card>
        <template #header>
          <div class="list-head">
            <span>处方记录</span>
            <div style="display:flex;gap:12px;align-items:center">
              <el-select v-model="filterStatus" style="width:120px" @change="loadList">
                <el-option label="全部状态" value="" />
                <el-option label="待付药" value="待付药" />
                <el-option label="已付药" value="已付药" />
                <el-option label="已收费" value="已收费" />
                <el-option label="已作废" value="已作废" />
              </el-select>
              <el-input v-model="filterKw" placeholder="患者 / 单号" clearable style="width:180px"
                @keyup.enter="loadList" @clear="loadList">
                <template #append><el-button :icon="'Search'" @click="loadList" /></template>
              </el-input>
            </div>
          </div>
        </template>
        <el-table :data="list" v-loading="loading" size="small" border>
          <el-table-column prop="no" label="单号" width="90" />
          <el-table-column prop="owner_type" label="对象" width="70" />
          <el-table-column prop="patient_name" label="患者" min-width="100" show-overflow-tooltip />
          <el-table-column prop="doses" label="剂数" width="60" />
          <el-table-column label="合计" width="90">
            <template #default="{ row }">{{ row.total.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="开方时间" width="150" />
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button size="small" :icon="'Printer'" @click="printOne(row)">打印</el-button>
              <el-button v-if="row.status === '待付药'" size="small" type="primary" plain @click="dispenseOne(row)">付药</el-button>
              <el-button v-if="row.status === '待付药'" size="small" @click="editOne(row)">修改</el-button>
              <el-button v-if="['待付药', '已付药'].includes(row.status)" size="small" type="danger" plain @click="voidOne(row)">作废</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination style="margin-top:12px;justify-content:flex-end" layout="total, prev, pager, next"
          :total="listTotal" :page-size="size" :current-page="page" @current-change="p => { page = p; loadList() }" />
      </el-card>
    </main>

    <PrintPreview v-model:visible="printVisible" :html="printHtml" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import ItemSelect from '../components/ItemSelect.vue'
import PrintPreview from '../components/PrintPreview.vue'

const form = reactive({ owner_type: '散户', patient_id: null, patient_name: '', doses: 7, usage_method: '', note: '', lines: [] })
const saving = ref(false)
const editingId = ref(0)
const patientOptions = ref([])
const searching = ref(false)
const list = ref([])
const listTotal = ref(0)
const page = ref(1)
const size = 20
const filterStatus = ref('')
const filterKw = ref('')
const loading = ref(false)
const printVisible = ref(false)
const printHtml = ref('')

const perDose = computed(() => form.lines.reduce((s, l) => s + (l.price || 0) * (l.qty || 0), 0))
const total = computed(() => perDose.value * (form.doses || 0))

function onItem(row, item) {
  row.price = item ? item.price : 0
  row.unit = item ? (item.unit || '克') : '克'
}

async function searchPatients(q) {
  searching.value = true
  try {
    if (form.owner_type === '住院') {
      // 住院只能从在院名单中选
      const r = await api(`/admissions?status=${encodeURIComponent('在院')}&keyword=${encodeURIComponent(q || '')}&size=100`)
      patientOptions.value = r.items.map(a => ({
        id: a.patient_id,
        label: `${a.patient_name}（住院号 ${a.no}）`,
      }))
    } else {
      if (!q) { patientOptions.value = []; return }
      const r = await api(`/patients?keyword=${encodeURIComponent(q)}&size=20`)
      patientOptions.value = r.items.map(p => ({
        id: p.id,
        label: `${p.name}（${p.no}，${p.phone}）`,
      }))
    }
  } catch { /* 忽略 */ } finally { searching.value = false }
}

async function onOwnerChange() {
  form.patient_id = null
  form.patient_name = ''
  if (form.owner_type === '住院') await searchPatients('')
}

async function loadList() {
  loading.value = true
  try {
    const r = await api(`/prescriptions?status=${encodeURIComponent(filterStatus.value)}&keyword=${encodeURIComponent(filterKw.value)}&page=${page.value}&size=${size}`)
    list.value = r.items
    listTotal.value = r.total
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

async function save() {
  const lines = form.lines.filter(l => l.item_id)
  if (form.owner_type === '住院' && !form.patient_id) return ElMessage.warning('住院处方必须选择患者')
  if (!lines.length) return ElMessage.warning('请至少添加一味药')
  saving.value = true
  try {
    const body = { ...form, lines: lines.map(l => ({ item_id: l.item_id, qty: l.qty })) }
    if (editingId.value) {
      await api(`/prescriptions/${editingId.value}`, { method: 'PUT', body })
      ElMessage.success('修改已保存')
    } else {
      await api('/prescriptions', { method: 'POST', body })
      ElMessage.success('处方已保存，状态：待付药')
    }
    editingId.value = 0
    form.patient_id = null; form.patient_name = ''; form.usage_method = ''; form.note = ''; form.lines = []
    loadList()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

function cancelEdit() {
  editingId.value = 0
  form.patient_id = null; form.patient_name = ''; form.usage_method = ''; form.note = ''; form.lines = []
}

async function editOne(row) {
  const d = await api(`/prescriptions/${row.id}`)
  editingId.value = d.id
  form.owner_type = d.owner_type
  form.patient_id = d.patient_id
  form.patient_name = ''
  form.doses = d.doses
  form.usage_method = d.usage_method
  form.note = d.note
  form.lines = d.lines.map(l => ({ item_id: l.item_id, qty: l.qty, price: l.price, unit: l.unit }))
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function dispenseOne(row) {
  try {
    await ElMessageBox.confirm(`确认为 ${row.patient_name} 付药吗？付药将立即扣减库存。`, '付药', { type: 'warning' })
  } catch { return }
  try {
    await api(`/prescriptions/${row.id}/dispense`, { method: 'POST' })
    ElMessage.success('已付药，库存已扣减；收费请到「收费结算」')
    loadList()
  } catch (e) { ElMessage.error(e.message) }
}

async function voidOne(row) {
  try {
    await ElMessageBox.confirm(`确定作废处方 ${row.no} 吗？${row.status === '已付药' ? '已扣的库存将退回。' : ''}`, '作废', { type: 'warning' })
  } catch { return }
  try {
    await api(`/prescriptions/${row.id}/void`, { method: 'POST' })
    ElMessage.success('已作废')
    loadList()
  } catch (e) { ElMessage.error(e.message) }
}

async function printOne(row) {
  const d = await api(`/prescriptions/${row.id}`)
  const { html } = await api('/print/preview', { method: 'POST', body: { template: 'prescription', data: { rx: d, lines: d.lines } } })
  printHtml.value = html
  printVisible.value = true
}

function statusType(s) {
  return { 待付药: 'warning', 已付药: 'primary', 已收费: 'success', 已作废: 'info' }[s] || 'info'
}

onMounted(loadList)
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; display: flex; flex-direction: column; gap: 20px; }
.total { font-size: 15px; }
.actions { padding-left: 90px; }
.list-head { display: flex; justify-content: space-between; align-items: center; }
</style>
