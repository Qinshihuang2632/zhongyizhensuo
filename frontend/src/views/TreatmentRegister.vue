<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">项目登记 · 治疗单</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <el-card class="editor">
        <template #header>登记新治疗单</template>
        <el-form label-width="90px">
          <el-row :gutter="12">
            <el-col :span="10">
              <el-form-item label="对象类型">
                <el-radio-group v-model="form.owner_type" @change="onOwnerChange">
                  <el-radio-button value="散户">散户</el-radio-button>
                  <el-radio-button value="住院">住院</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="14">
              <el-form-item label="患者" :required="form.owner_type === '住院'">
                <el-select
                  v-model="form.patient_id"
                  filterable
                  remote
                  clearable
                  :remote-method="searchPatients"
                  :loading="searching"
                  :placeholder="form.owner_type === '住院' ? '选择在院患者（可输入姓名过滤）' : '输入姓名 / 电话搜索患者档案'"
                  style="width:100%"
                >
                  <el-option v-for="p in patientOptions" :key="p.id" :label="p.label" :value="p.id" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item v-if="form.owner_type === '散户' && !form.patient_id" label="散户姓名">
            <el-input v-model="form.patient_name" placeholder="无档案时填写，留空记为「散户」" maxlength="50" style="width:280px" />
          </el-form-item>
          <el-form-item v-if="form.owner_type === '住院'" label=" ">
            <span class="hint">住院患者只能从「在院名单」中选择；新患者请先到「住院手续」页面办理入院。</span>
          </el-form-item>

          <el-form-item label="治疗项目">
            <div style="width:100%">
              <el-table :data="form.lines" size="small" border>
                <el-table-column label="项目" min-width="240">
                  <template #default="{ row }">
                    <ItemSelect v-model="row.item_id" :categories="['治疗项目']" @change="it => onItemChange(row, it)" />
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
              <div style="margin-top:8px;display:flex;align-items:center;gap:16px">
                <el-button size="small" type="primary" plain :icon="'Plus'" @click="addLine">添加项目</el-button>
                <span class="total">合计：<b>¥ {{ total.toFixed(2) }}</b></span>
              </div>
            </div>
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="10">
              <el-form-item label="治疗时间">
                <el-date-picker
                  v-model="form.treatment_time"
                  type="datetime"
                  value-format="YYYY-MM-DD HH:mm"
                  format="YYYY-MM-DD HH:mm"
                  placeholder="默认为当前时间，可改为实际治疗时间"
                  style="width:100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="14">
              <el-form-item label="备注">
                <el-input v-model="form.note" maxlength="200" />
              </el-form-item>
            </el-col>
          </el-row>
          <div class="actions">
            <el-button type="primary" :loading="saving" @click="save">保存登记（待收费）</el-button>
            <el-button v-if="editingId" @click="cancelEdit">取消修改</el-button>
          </div>
        </el-form>
      </el-card>

      <el-card>
        <template #header>
          <div class="list-head">
            <span>登记记录</span>
            <div style="display:flex;gap:12px;align-items:center">
              <el-select v-model="filterStatus" style="width:120px" @change="loadOrders">
                <el-option label="全部状态" value="" />
                <el-option label="待收费" value="待收费" />
                <el-option label="已收费" value="已收费" />
                <el-option label="已作废" value="已作废" />
              </el-select>
              <el-input
                v-model="filterKw"
                placeholder="患者 / 单号"
                clearable
                style="width:180px"
                @keyup.enter="loadOrders"
                @clear="loadOrders"
              >
                <template #append><el-button :icon="'Search'" @click="loadOrders" /></template>
              </el-input>
            </div>
          </div>
        </template>
        <el-table :data="orders" v-loading="ordersLoading" size="small" border>
          <el-table-column prop="no" label="单号" width="80" />
          <el-table-column prop="owner_type" label="对象" width="70" />
          <el-table-column prop="patient_name" label="患者" min-width="110" show-overflow-tooltip />
          <el-table-column prop="lines_count" label="项目数" width="70" />
          <el-table-column label="金额" width="100">
            <template #default="{ row }">{{ row.total.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="治疗时间" width="140">
            <template #default="{ row }">{{ row.treatment_time || row.created_at }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="登记时间" width="140" />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button size="small" :icon="'Printer'" @click="printOne(row)">打印</el-button>
              <template v-if="row.status === '待收费'">
                <el-button size="small" @click="editOne(row)">修改</el-button>
                <el-button size="small" type="danger" plain @click="voidOne(row)">作废</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          style="margin-top:12px;justify-content:flex-end"
          layout="total, prev, pager, next"
          :total="ordersTotal"
          :page-size="ordersSize"
          :current-page="ordersPage"
          @current-change="p => { ordersPage = p; loadOrders() }"
        />
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

const form = reactive({
  owner_type: '散户',
  patient_id: null,
  patient_name: '',
  note: '',
  treatment_time: '',
  lines: [],
})
const saving = ref(false)
const editingId = ref(0)
const patientOptions = ref([])
const searching = ref(false)

const orders = ref([])
const ordersTotal = ref(0)
const ordersPage = ref(1)
const ordersSize = 20
const filterStatus = ref('')
const filterKw = ref('')
const ordersLoading = ref(false)
const printVisible = ref(false)
const printHtml = ref('')

const total = computed(() =>
  form.lines.reduce((s, l) => s + (l.price || 0) * (l.qty || 0), 0),
)

function resetPatient() {
  form.patient_id = null
  form.patient_name = ''
}

async function onOwnerChange() {
  resetPatient()
  if (form.owner_type === '住院') await searchPatients('')
}

async function searchPatients(query) {
  searching.value = true
  try {
    if (form.owner_type === '住院') {
      // 住院只能从在院名单中选
      const r = await api(`/admissions?status=${encodeURIComponent('在院')}&keyword=${encodeURIComponent(query || '')}&size=100`)
      patientOptions.value = r.items.map(a => ({
        id: a.patient_id,
        label: `${a.patient_name}（住院号 ${a.no}）`,
      }))
    } else {
      if (!query) { patientOptions.value = []; return }
      // 散户不能选在院患者（在院期间费用走住院账户）
      const r = await api(`/patients?keyword=${encodeURIComponent(query)}&size=20&exclude_inpatient=1`)
      patientOptions.value = r.items.map(p => ({
        id: p.id,
        label: `${p.name}（${p.no}，${p.phone}）`,
      }))
    }
  } catch { /* 忽略瞬时错误 */ } finally {
    searching.value = false
  }
}

function addLine() {
  form.lines.push({ item_id: null, qty: 1, price: 0 })
}

function onItemChange(row, item) {
  row.price = item ? item.price : 0
}

async function loadOrders() {
  ordersLoading.value = true
  try {
    const params = `owner_type=&status=${encodeURIComponent(filterStatus.value)}` +
      `&keyword=${encodeURIComponent(filterKw.value)}&page=${ordersPage.value}&size=${ordersSize}`
    const r = await api('/treatment-orders?' + params)
    orders.value = r.items
    ordersTotal.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    ordersLoading.value = false
  }
}

function validate() {
  if (form.owner_type === '住院' && !form.patient_id) return '住院治疗单必须选择患者'
  const lines = form.lines.filter(l => l.item_id)
  if (!lines.length) return '请至少添加一个治疗项目'
  if (lines.some(l => !l.qty || l.qty <= 0)) return '数量必须大于 0'
  return ''
}

async function save() {
  const err = validate()
  if (err) return ElMessage.warning(err)
  saving.value = true
  try {
    const body = {
      owner_type: form.owner_type,
      patient_id: form.patient_id,
      patient_name: form.patient_name,
      note: form.note,
      treatment_time: form.treatment_time,
      lines: form.lines.filter(l => l.item_id).map(l => ({ item_id: l.item_id, qty: l.qty })),
    }
    if (editingId.value) {
      await api(`/treatment-orders/${editingId.value}`, { method: 'PUT', body })
      ElMessage.success('修改已保存')
    } else {
      await api('/treatment-orders', { method: 'POST', body })
      ElMessage.success('登记成功，状态：待收费')
    }
    resetForm()
    ordersPage.value = 1
    loadOrders()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function resetForm() {
  editingId.value = 0
  resetPatient()
  form.note = ''
  form.treatment_time = ''
  form.lines = []
}

function cancelEdit() {
  resetForm()
  ElMessage.info('已取消修改')
}

async function editOne(row) {
  try {
    const o = await api(`/treatment-orders/${row.id}`)
    editingId.value = o.id
    form.owner_type = o.owner_type
    form.patient_id = o.patient_id
    form.patient_name = o.patient_id ? '' : (o.patient_name === '散户' ? '' : o.patient_name)
    form.note = o.note
    form.treatment_time = o.treatment_time || ''
    form.lines = o.lines.map(l => ({ item_id: l.item_id, qty: l.qty, price: l.price }))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function voidOne(row) {
  try {
    await ElMessageBox.confirm(`确定作废治疗单 ${row.no}（${row.patient_name}）吗？作废后不可恢复。`, '作废', {
      type: 'warning', confirmButtonText: '作废', cancelButtonText: '取消',
    })
  } catch { return }
  try {
    await api(`/treatment-orders/${row.id}/void`, { method: 'POST' })
    ElMessage.success('已作废')
    loadOrders()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function printOne(row) {
  try {
    const o = await api(`/treatment-orders/${row.id}`)
    const { html } = await api('/print/preview', {
      method: 'POST',
      body: { template: 'treatment_order', data: { order: o, lines: o.lines } },
    })
    printHtml.value = html
    printVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function statusType(s) {
  return s === '待收费' ? 'warning' : s === '已收费' ? 'success' : 'info'
}

onMounted(loadOrders)
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; display: flex; flex-direction: column; gap: 20px; }
.hint { color: #b45309; font-size: 13px; }
.total { font-size: 15px; }
.actions { padding-left: 90px; }
.list-head { display: flex; justify-content: space-between; align-items: center; }
</style>
