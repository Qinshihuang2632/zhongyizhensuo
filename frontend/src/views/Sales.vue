<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">药品销售 · 中成药 / 西药 / 协定方</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <el-card>
        <template #header>开新销售单</template>
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
          <el-form-item label="明细">
            <div style="width:100%">
              <el-table :data="form.lines" size="small" border>
                <el-table-column label="品名" min-width="240">
                  <template #default="{ row }">
                    <ItemSelect v-if="row.line_type === 'item'" v-model="row.ref_id" :categories="['中成药', '西药', '中药饮片']" @change="it => onItem(row, it)" />
                    <el-select v-else v-model="row.ref_id" filterable placeholder="选择协定方" style="width:100%" @change="onFormula(row)">
                      <el-option v-for="f in formulas" :key="f.id" :label="`${f.name}（${f.price.toFixed(2)}元/剂）`" :value="f.id" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="类型" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.line_type === 'formula' ? 'warning' : 'info'">
                      {{ row.line_type === 'formula' ? '协定方' : '药品' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="单价" width="100">
                  <template #default="{ row }">{{ (row.price || 0).toFixed(2) }}</template>
                </el-table-column>
                <el-table-column label="数量" width="140">
                  <template #default="{ row }">
                    <el-input-number v-model="row.qty" :min="0.01" :max="9999" :step="1" size="small" style="width:100%" />
                  </template>
                </el-table-column>
                <el-table-column label="金额" width="100">
                  <template #default="{ row }">{{ ((row.price || 0) * (row.qty || 0)).toFixed(2) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="70">
                  <template #default="{ $index }">
                    <el-button size="small" type="danger" plain :icon="'Delete'" @click="form.lines.splice($index, 1)" />
                  </template>
                </el-table-column>
              </el-table>
              <div style="margin-top:8px;display:flex;align-items:center;gap:12px">
                <el-button size="small" type="primary" plain :icon="'Plus'" @click="addItemLine">加药品</el-button>
                <el-button size="small" type="warning" plain :icon="'Plus'" @click="addFormulaLine">加协定方</el-button>
                <span class="total">合计：<b>¥ {{ total.toFixed(2) }}</b></span>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="备注"><el-input v-model="form.note" maxlength="200" style="width:420px" /></el-form-item>
          <div class="actions">
            <el-button type="primary" :loading="saving" @click="save">保存销售单（扣库存，待收费）</el-button>
          </div>
        </el-form>
      </el-card>

      <el-card>
        <template #header>
          <div class="list-head">
            <span>销售记录</span>
            <div style="display:flex;gap:12px;align-items:center">
              <el-select v-model="filterStatus" style="width:120px" @change="loadList">
                <el-option label="全部状态" value="" />
                <el-option label="待收费" value="待收费" />
                <el-option label="已收费" value="已收费" />
                <el-option label="已作废" value="已作废" />
                <el-option label="已退费" value="已退费" />
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
          <el-table-column prop="lines_count" label="行数" width="60" />
          <el-table-column label="合计" width="90">
            <template #default="{ row }">{{ row.total.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="150" />
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" :icon="'Printer'" @click="printOne(row)">打印</el-button>
              <el-button v-if="row.status === '待收费'" size="small" type="danger" plain @click="voidOne(row)">作废</el-button>
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

const form = reactive({ owner_type: '散户', patient_id: null, patient_name: '', note: '', lines: [] })
const saving = ref(false)
const patientOptions = ref([])
const searching = ref(false)
const formulas = ref([])
const list = ref([])
const listTotal = ref(0)
const page = ref(1)
const size = 20
const filterStatus = ref('')
const filterKw = ref('')
const loading = ref(false)
const printVisible = ref(false)
const printHtml = ref('')

const total = computed(() => form.lines.reduce((s, l) => s + (l.price || 0) * (l.qty || 0), 0))

function addItemLine() {
  form.lines.push({ line_type: 'item', ref_id: null, qty: 1, price: 0 })
}
function addFormulaLine() {
  form.lines.push({ line_type: 'formula', ref_id: null, qty: 1, price: 0 })
}
function onItem(row, item) {
  row.price = item ? item.price : 0
}
function onFormula(row) {
  row.price = formulas.value.find(f => f.id === row.ref_id)?.price || 0
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
      // 散户不能选在院患者（在院期间费用走住院账户）
      const r = await api(`/patients?keyword=${encodeURIComponent(q)}&size=20&exclude_inpatient=1`)
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

async function loadFormulas() {
  try {
    formulas.value = (await api('/formulas')).filter(f => f.active)
  } catch { /* 忽略 */ }
}

async function loadList() {
  loading.value = true
  try {
    const r = await api(`/sales?status=${encodeURIComponent(filterStatus.value)}&keyword=${encodeURIComponent(filterKw.value)}&page=${page.value}&size=${size}`)
    list.value = r.items
    listTotal.value = r.total
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

async function save() {
  const lines = form.lines.filter(l => l.ref_id)
  if (form.owner_type === '住院' && !form.patient_id) return ElMessage.warning('住院销售单必须选择患者')
  if (!lines.length) return ElMessage.warning('请至少添加一行明细')
  saving.value = true
  try {
    const r = await api('/sales', {
      method: 'POST',
      body: { owner_type: form.owner_type, patient_id: form.patient_id, patient_name: form.patient_name,
              note: form.note, lines: lines.map(l => ({ line_type: l.line_type, ref_id: l.ref_id, qty: l.qty })) },
    })
    ElMessage.success(`销售单 ${r.no} 已保存（扣库存），合计 ¥${r.total}；收费请到「收费结算」`)
    form.patient_id = null; form.patient_name = ''; form.note = ''; form.lines = []
    loadList()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function voidOne(row) {
  try {
    await ElMessageBox.confirm(`确定作废销售单 ${row.no} 吗？已扣库存将退回。`, '作废', { type: 'warning' })
  } catch { return }
  try {
    await api(`/sales/${row.id}/void`, { method: 'POST' })
    ElMessage.success('已作废，库存已退回')
    loadList()
  } catch (e) { ElMessage.error(e.message) }
}

async function printOne(row) {
  const d = await api(`/sales/${row.id}`)
  const { html } = await api('/print/preview', { method: 'POST', body: { template: 'sale', data: { sale: d, lines: d.lines } } })
  printHtml.value = html
  printVisible.value = true
}

function statusType(s) {
  return { 待收费: 'warning', 已收费: 'success', 已作废: 'info', 已退费: 'danger' }[s] || 'info'
}

onMounted(() => { loadList(); loadFormulas() })
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
