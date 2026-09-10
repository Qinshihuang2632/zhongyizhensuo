<template>
  <div>
    <el-tabs v-model="tab" @tab-change="load">
      <el-tab-pane label="入库登记" name="in" />
      <el-tab-pane label="入库记录" name="inlist" />
      <el-tab-pane label="库存与预警" name="stock" />
      <el-tab-pane label="出入库流水" name="moves" />
    </el-tabs>

    <!-- 入库登记 -->
    <template v-if="tab === 'in'">
      <div style="display:flex;gap:16px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <el-input v-model="inForm.supplier" placeholder="供应商（选填）" style="width:220px" maxlength="50" />
        <el-input v-model="inForm.note" placeholder="备注（选填）" style="width:220px" maxlength="200" />
      </div>
      <el-table :data="inForm.lines" size="small" border>
        <el-table-column label="药品" min-width="220">
          <template #default="{ row }">
            <ItemSelect v-model="row.item_id" :categories="['中药饮片', '中成药', '西药']" @change="() => {}" />
          </template>
        </el-table-column>
        <el-table-column label="数量" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.qty" :min="0.01" :max="999999" :step="1" size="small" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column label="进价" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.cost" :min="0" :max="999999" :precision="2" size="small" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column label="批号" width="120">
          <template #default="{ row }"><el-input v-model="row.batch_no" size="small" maxlength="30" /></template>
        </el-table-column>
        <el-table-column label="效期" width="150">
          <template #default="{ row }">
            <el-date-picker v-model="row.expiry" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="90">
          <template #default="{ row }">{{ ((row.qty || 0) * (row.cost || 0)).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="70">
          <template #default="{ $index }">
            <el-button size="small" type="danger" plain :icon="'Delete'" @click="inForm.lines.splice($index, 1)" />
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top:10px;display:flex;gap:16px;align-items:center">
        <el-button size="small" type="primary" plain :icon="'Plus'" @click="inForm.lines.push(newInLine())">加一行</el-button>
        <el-button type="primary" :loading="saving" @click="saveIn">保存入库单</el-button>
        <span>合计进价：¥ {{ inTotal.toFixed(2) }}</span>
      </div>
    </template>

    <!-- 入库记录 -->
    <template v-else-if="tab === 'inlist'">
      <el-table :data="inList" v-loading="loading" size="small" border>
        <el-table-column prop="no" label="单号" width="100" />
        <el-table-column prop="supplier" label="供应商" min-width="120" />
        <el-table-column prop="lines_count" label="行数" width="60" />
        <el-table-column label="进价合计" width="110">
          <template #default="{ row }">¥ {{ row.total_cost.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button size="small" @click="showIn(row)">明细</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 库存与预警 -->
    <template v-else-if="tab === 'stock'">
      <div class="bar">
        <el-select v-model="stockCategory" style="width:130px" @change="loadStock">
          <el-option label="全部药品" value="" />
          <el-option label="中药饮片" value="中药饮片" />
          <el-option label="中成药" value="中成药" />
          <el-option label="西药" value="西药" />
        </el-select>
        <el-select v-model="stockAlert" style="width:140px" @change="loadStock">
          <el-option label="全部" value="" />
          <el-option label="仅低库存" value="low" />
          <el-option label="仅近效期" value="near_expiry" />
        </el-select>
        <el-input v-model="stockKw" placeholder="品名 / 编号" clearable style="width:180px"
          @keyup.enter="loadStock" @clear="loadStock">
          <template #append><el-button :icon="'Search'" @click="loadStock" /></template>
        </el-input>
      </div>
      <el-table :data="stockList" v-loading="loading" size="small" border max-height="430">
        <el-table-column prop="no" label="编号" width="80" />
        <el-table-column prop="name" label="品名" min-width="120" />
        <el-table-column prop="category" label="类别" width="90" />
        <el-table-column label="现存量" width="100">
          <template #default="{ row }">
            <span :style="{ color: row.low ? '#c0392b' : '', fontWeight: row.low ? 'bold' : '' }">
              {{ row.qty }} {{ row.unit }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="min_stock" label="低库存线" width="90" />
        <el-table-column label="近效期批次" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.near_expiry" type="danger" size="small">{{ row.near_expiry }} 批</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="showBatches(row)">批次</el-button>
            <el-button size="small" type="warning" plain @click="openAdjust(row)">调整</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 出入库流水 -->
    <template v-else>
      <el-table :data="moves" v-loading="loading" size="small" border max-height="470">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="item_name" label="品名" min-width="110" />
        <el-table-column prop="direction" label="方向" width="70" />
        <el-table-column label="数量" width="90">
          <template #default="{ row }">{{ row.qty }} {{ row.unit }}</template>
        </el-table-column>
        <el-table-column prop="ref_no" label="关联单号" width="110" />
        <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
      </el-table>
    </template>

    <!-- 入库明细 -->
    <el-dialog v-model="inDetailVisible" title="入库单明细" width="640px">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="单号">{{ inDetail.no }}</el-descriptions-item>
        <el-descriptions-item label="供应商">{{ inDetail.supplier || '—' }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="inDetail.lines" size="small" border style="margin-top:10px">
        <el-table-column prop="item_name" label="药品" min-width="110" />
        <el-table-column label="数量" width="90"><template #default="{ row }">{{ row.qty }} {{ row.unit }}</template></el-table-column>
        <el-table-column label="进价" width="90"><template #default="{ row }">{{ row.cost.toFixed(2) }}</template></el-table-column>
        <el-table-column prop="batch_no" label="批号" width="90" />
        <el-table-column prop="expiry" label="效期" width="100" />
      </el-table>
    </el-dialog>

    <!-- 批次 -->
    <el-dialog v-model="batchVisible" :title="`批次明细 · ${batchItem?.name || ''}`" width="560px">
      <el-table :data="batches" size="small" border>
        <el-table-column prop="batch_no" label="批号" width="110">
          <template #default="{ row }">{{ row.batch_no || '—' }}</template>
        </el-table-column>
        <el-table-column label="现存" width="110">
          <template #default="{ row }">{{ row.qty }} {{ batchItem?.unit }}</template>
        </el-table-column>
        <el-table-column prop="expiry" label="效期" width="110">
          <template #default="{ row }">{{ row.expiry || '—' }}</template>
        </el-table-column>
        <el-table-column prop="source" label="来源" min-width="90" />
      </el-table>
    </el-dialog>

    <!-- 库存调整 -->
    <el-dialog v-model="adjustVisible" title="库存调整（报损 / 盘盈亏）" width="420px">
      <el-form label-width="90px">
        <el-form-item label="品名"><span>{{ adjustItem?.name }}（现存 {{ adjustQty }} {{ adjustItem?.unit }}）</span></el-form-item>
        <el-form-item label="调整数量">
          <el-input-number v-model="adjustDelta" :step="1" style="width:160px" />
          <span class="hint">正数=盘盈增加，负数=报损/盘亏减少</span>
        </el-form-item>
        <el-form-item label="原因"><el-input v-model="adjustNote" maxlength="100" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAdjust">确认调整</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import ItemSelect from './ItemSelect.vue'

const tab = ref('in')
const loading = ref(false)
const saving = ref(false)

// 入库登记
const newInLine = () => ({ item_id: null, qty: 1, cost: 0, batch_no: '', expiry: '' })
const inForm = ref({ supplier: '', note: '', lines: [newInLine()] })
const inTotal = computed(() => inForm.value.lines.reduce((s, l) => s + (l.qty || 0) * (l.cost || 0), 0))

// 入库记录
const inList = ref([])
const inDetailVisible = ref(false)
const inDetail = ref({ lines: [] })

// 库存
const stockList = ref([])
const stockCategory = ref('')
const stockAlert = ref('')
const stockKw = ref('')
const batchVisible = ref(false)
const batches = ref([])
const batchItem = ref(null)
const adjustVisible = ref(false)
const adjustItem = ref(null)
const adjustQty = ref(0)
const adjustDelta = ref(0)
const adjustNote = ref('')

// 流水
const moves = ref([])

async function load() {
  loading.value = true
  try {
    if (tab.value === 'inlist') {
      inList.value = (await api('/stock/in?size=50')).items
    } else if (tab.value === 'stock') {
      await loadStock()
    } else if (tab.value === 'moves') {
      moves.value = (await api('/stock/moves?size=100')).items
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadStock() {
  loading.value = true
  try {
    const params = `category=${encodeURIComponent(stockCategory.value)}&alert=${stockAlert.value}&keyword=${encodeURIComponent(stockKw.value)}`
    stockList.value = (await api('/stock?' + params)).items
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function saveIn() {
  const lines = inForm.value.lines.filter(l => l.item_id)
  if (!lines.length) return ElMessage.warning('请至少添加一行药品')
  saving.value = true
  try {
    const r = await api('/stock/in', {
      method: 'POST',
      body: { supplier: inForm.value.supplier, note: inForm.value.note, lines: lines.map(l => ({ ...l })) },
    })
    ElMessage.success(`入库完成：${r.no}，进价合计 ¥${r.total_cost}`)
    inForm.value = { supplier: '', note: '', lines: [newInLine()] }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function showIn(row) {
  inDetail.value = await api(`/stock/in/${row.id}`)
  inDetailVisible.value = true
}

async function showBatches(row) {
  batchItem.value = row
  batches.value = await api(`/stock/${row.id}/batches`)
  batchVisible.value = true
}

function openAdjust(row) {
  adjustItem.value = row
  adjustQty.value = row.qty
  adjustDelta.value = 0
  adjustNote.value = ''
  adjustVisible.value = true
}

async function saveAdjust() {
  if (!adjustDelta.value) return ElMessage.warning('调整数量不能为 0')
  saving.value = true
  try {
    await api('/stock/adjust', {
      method: 'POST',
      body: { item_id: adjustItem.value.id, delta: adjustDelta.value, note: adjustNote.value },
    })
    ElMessage.success('库存已调整')
    adjustVisible.value = false
    loadStock()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.bar { display: flex; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #888; font-size: 12px; margin-left: 10px; }
</style>
