<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">查询中心</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <el-tabs v-model="tab" @tab-change="load">
        <el-tab-pane label="收费流水" name="charges" />
        <el-tab-pane label="出入库流水" name="stock" />
        <el-tab-pane label="综合查询" name="summary" />
        <el-tab-pane label="日结" name="daily" />
      </el-tabs>

      <div class="bar" v-if="tab !== 'daily'">
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="开始日期" end-placeholder="结束日期" style="width:260px" @change="load" />
        <el-select v-if="tab === 'charges'" v-model="chargeType" style="width:120px" @change="load">
          <el-option label="全部款类" value="" />
          <el-option label="收费" value="收费" />
          <el-option label="退费" value="退费" />
          <el-option label="预交款" value="预交款" />
          <el-option label="出院结算" value="出院结算" />
        </el-select>
        <el-select v-if="tab === 'stock'" v-model="moveDir" style="width:120px" @change="load">
          <el-option label="全部方向" value="" />
          <el-option label="入库" value="入库" />
          <el-option label="出库" value="出库" />
          <el-option label="退回" value="退回" />
          <el-option label="调整" value="调整" />
        </el-select>
        <el-input v-model="kw" placeholder="患者 / 品名 / 单号" clearable style="width:220px"
          @keyup.enter="load" @clear="load">
          <template #append><el-button :icon="'Search'" @click="load" /></template>
        </el-input>
      </div>

      <!-- 收费流水 -->
      <template v-if="tab === 'charges'">
        <el-table :data="rows" v-loading="loading" size="small" border max-height="460">
          <el-table-column label="单号" width="100"><template #default="{ row }">SF{{ String(row.id).padStart(6, '0') }}</template></el-table-column>
          <el-table-column prop="no_type" label="款类" width="90" />
          <el-table-column prop="patient_name" label="患者" min-width="100" show-overflow-tooltip />
          <el-table-column label="业务单据" width="110">
            <template #default="{ row }">{{ row.source_no || '—' }}</template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <span :style="{ color: row.amount < 0 ? '#c0392b' : '' }">¥ {{ row.amount.toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="method" label="方式" width="80" />
          <el-table-column prop="created_at" label="时间" width="160" />
        </el-table>
      </template>

      <!-- 出入库流水 -->
      <template v-else-if="tab === 'stock'">
        <el-table :data="rows" v-loading="loading" size="small" border max-height="460">
          <el-table-column prop="item_name" label="品名" min-width="120" />
          <el-table-column prop="category" label="类别" width="90" />
          <el-table-column prop="direction" label="方向" width="70" />
          <el-table-column label="数量" width="90">
            <template #default="{ row }">{{ row.qty }} {{ row.unit }}</template>
          </el-table-column>
          <el-table-column prop="ref_no" label="关联单号" width="110" />
          <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="160" />
        </el-table>
      </template>

      <!-- 综合查询 -->
      <template v-else-if="tab === 'summary'">
        <el-table :data="rows" v-loading="loading" size="small" border max-height="460">
          <el-table-column prop="patient_name" label="患者" min-width="120" />
          <el-table-column prop="times" label="收款笔数" width="100" />
          <el-table-column label="缴费合计" width="120">
            <template #default="{ row }">¥ {{ row.paid.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column label="退费合计" width="120">
            <template #default="{ row }">¥ {{ row.refunded.toFixed(2) }}</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- 日结 / 月结 / 年结 -->
      <template v-else>
        <div class="bar">
          <el-radio-group v-model="reportMode" @change="modeChanged">
            <el-radio-button value="daily">日结（可选日期范围）</el-radio-button>
            <el-radio-button value="monthly">月结（已结束的整月）</el-radio-button>
            <el-radio-button value="yearly">年结（已结束的整年）</el-radio-button>
          </el-radio-group>
          <el-date-picker v-if="reportMode === 'daily'" v-model="dateRange" type="daterange"
            value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期"
            clearable style="width:260px" @change="load" />
          <el-date-picker v-if="reportMode === 'monthly'" v-model="monthVal" type="month"
            value-format="YYYY-MM" placeholder="选择月份" :disabled-date="disableMonth" style="width:160px" @change="load" />
          <el-date-picker v-if="reportMode === 'yearly'" v-model="yearVal" type="year"
            value-format="YYYY" placeholder="选择年份" :disabled-date="disableYear" style="width:140px" @change="load" />
          <span class="mode-hint">{{ modeHint }}</span>
        </div>
        <el-card v-if="daily" style="max-width:640px">
          <template #header>
            <div class="list-head">
              <span>{{ modeTitle }} · {{ daily.period }}</span>
              <el-button size="small" :icon="'Printer'" @click="printDaily">打印{{ modeTitle }}</el-button>
            </div>
          </template>
          <div class="daily-grid">
            <div><span class="k">收款笔数</span><b>{{ daily.count }}</b></div>
            <div><span class="k">净收入（含预交/退费冲抵）</span><b>¥ {{ daily.income.toFixed(2) }}</b></div>
          </div>
          <el-descriptions title="按款类" :column="2" border size="small" style="margin-top:10px">
            <el-descriptions-item v-for="(v, k) in daily.by_type" :key="k" :label="k">¥ {{ v.toFixed(2) }}</el-descriptions-item>
          </el-descriptions>
          <el-descriptions title="按方式（收费/出院结算）" :column="2" border size="small" style="margin-top:10px">
            <el-descriptions-item v-for="(v, k) in daily.by_method" :key="k" :label="k">¥ {{ v.toFixed(2) }}</el-descriptions-item>
          </el-descriptions>
          <el-descriptions title="按业务类别（净额）" :column="2" border size="small" style="margin-top:10px">
            <el-descriptions-item v-for="(v, k) in daily.by_category" :key="k" :label="k">¥ {{ v.toFixed(2) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </template>

      <el-pagination v-if="tab !== 'daily'" style="margin-top:12px;justify-content:flex-end"
        layout="total, prev, pager, next" :total="total" :page-size="size" :current-page="page"
        @current-change="p => { page = p; load() }" />
    </main>

    <PrintPreview v-model:visible="printVisible" :html="printHtml" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import PrintPreview from '../components/PrintPreview.vue'

const tab = ref('charges')
const rows = ref([])
const total = ref(0)
const page = ref(1)
const size = 20
const kw = ref('')
const dateRange = ref(null)
const chargeType = ref('')
const moveDir = ref('')
const loading = ref(false)
const daily = ref(null)
const reportMode = ref('daily')
const monthVal = ref('')
const yearVal = ref('')
const printVisible = ref(false)
const printHtml = ref('')

const modeTitle = computed(() =>
  ({ daily: '日结', monthly: '月结单', yearly: '年结单' })[reportMode.value],
)
const modeHint = computed(() => ({
  daily: '不选日期 = 今天；选范围 = 区间汇总（可看本月至今）',
  monthly: '只能选择已结束的自然月；本月数据请用日结的日期范围查看',
  yearly: '只能选择已结束的自然年',
})[reportMode.value])

function disableMonth(d) {
  const dt = new Date(d)
  const now = new Date()
  return dt.getFullYear() > now.getFullYear() ||
    (dt.getFullYear() === now.getFullYear() && dt.getMonth() >= now.getMonth())
}
function disableYear(d) {
  return new Date(d).getFullYear() >= new Date().getFullYear()
}

function modeChanged() {
  daily.value = null
}

function dateParams() {
  if (!dateRange.value?.length) return ''
  return `&start=${dateRange.value[0]}&end=${dateRange.value[1]}`
}

async function load() {
  loading.value = true
  try {
    if (tab.value === 'charges') {
      daily.value = null
      const r = await api(`/charges?no_type=${encodeURIComponent(chargeType.value)}&keyword=${encodeURIComponent(kw.value)}${dateParams()}&page=${page.value}&size=${size}`)
      rows.value = r.items
      total.value = r.total
    } else if (tab.value === 'stock') {
      daily.value = null
      const r = await api(`/stock/moves?direction=${encodeURIComponent(moveDir.value)}&keyword=${encodeURIComponent(kw.value)}${dateParams()}&page=${page.value}&size=${size}`)
      rows.value = r.items
      total.value = r.total
    } else if (tab.value === 'summary') {
      daily.value = null
      rows.value = await api(`/queries/patients-summary?keyword=${encodeURIComponent(kw.value)}${dateParams()}`)
      total.value = rows.value.length
    } else {
      try {
        if (reportMode.value === 'monthly') {
          if (!monthVal.value) { daily.value = null; return }
          daily.value = await api(`/reports/monthly?month=${monthVal.value}`)
        } else if (reportMode.value === 'yearly') {
          if (!yearVal.value) { daily.value = null; return }
          daily.value = await api(`/reports/yearly?year=${yearVal.value}`)
        } else {
          if (dateRange.value?.length) {
            daily.value = await api(`/reports/daily?start=${dateRange.value[0]}&end=${dateRange.value[1]}`)
          } else {
            daily.value = await api('/reports/daily')
          }
        }
      } catch (e) {
        daily.value = null
        ElMessage.error(e.message)
      }
      rows.value = []
      total.value = 0
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function printDaily() {
  const title = { daily: '收费日结单', monthly: '收费月结单', yearly: '收费年结单' }[reportMode.value]
  const { html } = await api('/print/preview', { method: 'POST', body: { template: 'daily_report', data: { ...daily.value, title } } })
  printHtml.value = html
  printVisible.value = true
}

watch(tab, () => { page.value = 1 })
onMounted(load)
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; }
.bar { display: flex; gap: 16px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }
.mode-hint { color: #888; font-size: 13px; }
.list-head { display: flex; justify-content: space-between; align-items: center; }
.daily-grid { display: flex; gap: 28px; font-size: 14px; }
.daily-grid .k { color: #888; margin-right: 6px; }
</style>
