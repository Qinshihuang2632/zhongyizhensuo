<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">打印中心 · 单据补打</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <el-tabs v-model="tab" @tab-change="load">
        <el-tab-pane label="治疗项目单" name="treatment_order" />
        <el-tab-pane label="中药处方笺" name="prescription" />
        <el-tab-pane label="药品销售单" name="sale" />
        <el-tab-pane label="收费凭证" name="charge" />
      </el-tabs>

      <div class="bar">
        <el-input v-model="kw" placeholder="患者 / 单号" clearable style="width:240px"
          @keyup.enter="load" @clear="load">
          <template #append><el-button :icon="'Search'" @click="load" /></template>
        </el-input>
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="开始日期" end-placeholder="结束日期" style="width:260px" @change="load" />
      </div>

      <el-table :data="items" v-loading="loading" size="small" border max-height="480">
        <el-table-column label="单号" width="100">
          <template #default="{ row }">{{ prefix }}{{ String(row.id).padStart(6, '0') }}</template>
        </el-table-column>
        <el-table-column prop="patient_name" label="患者" min-width="110" show-overflow-tooltip />
        <el-table-column label="金额" width="100">
          <template #default="{ row }">¥ {{ (row.total ?? row.amount ?? 0).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column v-if="tab !== 'charge'" prop="status" label="状态" width="90" />
        <el-table-column v-else prop="no_type" label="类型" width="90" />
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain :icon="'Printer'" @click="printOne(row)">打印</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination style="margin-top:12px;justify-content:flex-end" layout="total, prev, pager, next"
        :total="total" :page-size="size" :current-page="page" @current-change="p => { page = p; load() }" />
    </main>

    <PrintPreview v-model:visible="printVisible" :html="printHtml" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import PrintPreview from '../components/PrintPreview.vue'

const tab = ref('treatment_order')
const items = ref([])
const total = ref(0)
const page = ref(1)
const size = 20
const kw = ref('')
const dateRange = ref(null)
const loading = ref(false)
const printVisible = ref(false)
const printHtml = ref('')

const conf = {
  treatment_order: { url: '/treatment-orders', prefix: 'TO', template: 'treatment_order' },
  prescription: { url: '/prescriptions', prefix: 'CF', template: 'prescription' },
  sale: { url: '/sales', prefix: 'XC', template: 'sale' },
  charge: { url: '/charges', prefix: 'SF', template: 'charge' },
}
const prefix = computed(() => conf[tab.value].prefix)

async function load() {
  loading.value = true
  try {
    let url = `${conf[tab.value].url}?keyword=${encodeURIComponent(kw.value)}&page=${page.value}&size=${size}`
    if (dateRange.value?.length) url += `&start=${dateRange.value[0]}&end=${dateRange.value[1]}`
    const r = await api(url)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function printOne(row) {
  try {
    let data
    if (tab.value === 'treatment_order') {
      const d = await api(`/treatment-orders/${row.id}`)
      data = { order: d, lines: d.lines }
    } else if (tab.value === 'prescription') {
      const d = await api(`/prescriptions/${row.id}`)
      data = { rx: d, lines: d.lines }
    } else if (tab.value === 'sale') {
      const d = await api(`/sales/${row.id}`)
      data = { sale: d, lines: d.lines }
    } else {
      data = { c: await api(`/charges/${row.id}`) }
    }
    const { html } = await api('/print/preview', { method: 'POST', body: { template: conf[tab.value].template, data } })
    printHtml.value = html
    printVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; }
.bar { display: flex; gap: 16px; margin-bottom: 14px; }
</style>
