<template>
  <div>
    <el-tabs v-model="tab" @tab-change="onTabChange">
      <el-tab-pane v-for="c in itemCategories" :key="c" :label="c" :name="c" />
      <el-tab-pane label="协定处方" name="协定处方" />
    </el-tabs>

    <!-- 药品 / 治疗项目 -->
    <template v-if="tab !== '协定处方'">
      <div class="bar">
        <el-input
          v-model="itemKw"
          placeholder="搜索：名称 / 规格 / 厂家 / 编号"
          clearable
          style="width:280px"
          @keyup.enter="searchItems"
          @clear="searchItems"
        >
          <template #append><el-button :icon="'Search'" @click="searchItems" /></template>
        </el-input>
        <el-button type="primary" :icon="'Plus'" @click="openItem()">新增</el-button>
        <el-switch v-model="showInactive" active-text="显示已停用" @change="loadItems" />
      </div>
      <el-table :data="items" v-loading="itemLoading" size="small" border max-height="420">
        <el-table-column prop="no" label="编号" width="80" />
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="unit" label="单位" width="70" />
        <el-table-column prop="spec" label="规格" min-width="110" show-overflow-tooltip />
        <el-table-column label="售价" width="90">
          <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="manufacturer" label="厂家" min-width="110" show-overflow-tooltip />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'success' : 'info'" size="small">{{ row.active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openItem(row)">修改</el-button>
            <el-button size="small" :type="row.active ? 'warning' : 'success'" plain @click="toggleItem(row)">
              {{ row.active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        style="margin-top:12px;justify-content:flex-end"
        layout="total, prev, pager, next"
        :total="itemTotal"
        :page-size="itemSize"
        :current-page="itemPage"
        @current-change="p => { itemPage = p; loadItems() }"
      />
    </template>

    <!-- 协定处方 -->
    <template v-else>
      <div class="bar">
        <el-input
          v-model="formulaKw"
          placeholder="搜索方名"
          clearable
          style="width:280px"
          @keyup.enter="loadFormulas"
          @clear="loadFormulas"
        >
          <template #append><el-button :icon="'Search'" @click="loadFormulas" /></template>
        </el-input>
        <el-button type="primary" :icon="'Plus'" @click="openFormula()">新增协定处方</el-button>
      </div>
      <el-table :data="formulas" v-loading="formulaLoading" size="small" border max-height="460">
        <el-table-column prop="no" label="编号" width="80" />
        <el-table-column prop="name" label="方名" min-width="130" />
        <el-table-column label="整方价" width="100">
          <template #default="{ row }">{{ row.price.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="组成" min-width="240">
          <template #default="{ row }">
            {{ row.lines.map(l => `${l.item_name}×${l.qty}`).join('、') || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'success' : 'info'" size="small">{{ row.active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openFormula(row)">修改</el-button>
            <el-button size="small" :type="row.active ? 'warning' : 'success'" plain @click="toggleFormula(row)">
              {{ row.active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 条目新增/修改 -->
    <el-dialog v-model="itemDialog" :title="itemForm.id ? '修改条目' : '新增' + tab" width="520px">
      <el-form label-width="90px">
        <el-form-item label="名称" required><el-input v-model="itemForm.name" maxlength="50" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="单位"><el-input v-model="itemForm.unit" maxlength="20" placeholder="如：次 / 盒 / 克" /></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="售价" required>
              <el-input-number v-model="itemForm.price" :min="0" :max="999999" :precision="2" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <template v-if="tab !== '治疗项目'">
          <el-row :gutter="12">
            <el-col :span="12"><el-form-item label="规格"><el-input v-model="itemForm.spec" maxlength="50" /></el-form-item></el-col>
            <el-col :span="12">
              <el-form-item label="进价">
                <el-input-number v-model="itemForm.cost" :min="0" :max="999999" :precision="2" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="厂家"><el-input v-model="itemForm.manufacturer" maxlength="50" /></el-form-item>
        </template>
        <el-form-item label="备注"><el-input v-model="itemForm.note" type="textarea" :rows="2" maxlength="200" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemDialog = false">取消</el-button>
        <el-button type="primary" :loading="itemSaving" @click="saveItem">保存</el-button>
      </template>
    </el-dialog>

    <!-- 协定处方新增/修改 -->
    <el-dialog v-model="formulaDialog" :title="formulaForm.id ? '修改协定处方' : '新增协定处方'" width="640px">
      <el-form v-if="formulaForm" label-width="90px">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="方名" required><el-input v-model="formulaForm.name" maxlength="50" /></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="整方价">
              <el-input-number v-model="formulaForm.price" :min="0" :max="999999" :precision="2" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="组成">
          <div style="width:100%">
            <div v-for="(l, i) in formulaForm.lines" :key="i" class="fline">
              <ItemSelect v-model="l.item_id" :categories="['中药饮片', '中成药', '西药']" style="flex:1" @change="() => {}" />
              <el-input-number v-model="l.qty" :min="0.01" :max="9999" :step="1" size="small" style="width:110px" />
              <span class="famount">{{ ((itemPrice(l.item_id) || 0) * (l.qty || 0)).toFixed(2) }}元</span>
              <el-button size="small" type="danger" plain :icon="'Delete'" @click="formulaForm.lines.splice(i, 1)" />
            </div>
            <el-button size="small" :icon="'Plus'" @click="formulaForm.lines.push({ item_id: null, qty: 1 })">加一味</el-button>
            <span style="margin-left:12px;color:#888;font-size:13px">组成小计：{{ formulaLinesTotal.toFixed(2) }} 元</span>
          </div>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="formulaForm.note" type="textarea" :rows="2" maxlength="200" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formulaDialog = false">取消</el-button>
        <el-button type="primary" :loading="formulaSaving" @click="saveFormula">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import ItemSelect from './ItemSelect.vue'

const itemCategories = ['治疗项目', '中成药', '西药', '中药饮片']
const tab = ref('治疗项目')

// ---- 条目 ----
const items = ref([])
const itemTotal = ref(0)
const itemPage = ref(1)
const itemSize = 50
const itemKw = ref('')
const showInactive = ref(false)
const itemLoading = ref(false)
const itemDialog = ref(false)
const itemSaving = ref(false)
const emptyItem = () => ({
  id: 0, name: '', unit: '', spec: '', price: 0, cost: 0, manufacturer: '', note: '',
})
const itemForm = ref(emptyItem())

async function loadItems() {
  itemLoading.value = true
  try {
    const params = `category=${encodeURIComponent(tab.value)}&keyword=${encodeURIComponent(itemKw.value)}&page=${itemPage.value}&size=${itemSize}` +
      (showInactive.value ? '' : '&active=1')
    const r = await api('/items?' + params)
    items.value = r.items
    itemTotal.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    itemLoading.value = false
  }
}

function searchItems() {
  itemPage.value = 1
  loadItems()
}

function onTabChange() {
  itemPage.value = 1
  itemKw.value = ''
  if (tab.value === '协定处方') loadFormulas()
  else loadItems()
}

function openItem(row) {
  itemForm.value = row
    ? { ...row }
    : { ...emptyItem() }
  itemDialog.value = true
}

async function saveItem() {
  const f = itemForm.value
  if (!f.name || !f.name.trim()) return ElMessage.warning('请填写名称')
  itemSaving.value = true
  try {
    const body = { ...f, category: tab.value }
    if (f.id) await api(`/items/${f.id}`, { method: 'PUT', body })
    else await api('/items', { method: 'POST', body })
    ElMessage.success('已保存')
    itemDialog.value = false
    loadItems()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    itemSaving.value = false
  }
}

async function toggleItem(row) {
  try {
    await api(`/items/${row.id}`, { method: 'PUT', body: { ...row, active: !row.active } })
    loadItems()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---- 协定处方 ----
const formulas = ref([])
const formulaKw = ref('')
const formulaLoading = ref(false)
const formulaDialog = ref(false)
const formulaSaving = ref(false)
// 不能初始为 null：对话框关闭时其标题等绑定也会求值，null 会导致整个组件渲染崩溃（白屏）
const formulaForm = ref({ id: 0, name: '', price: 0, note: '', active: true, lines: [] })
const allDrugs = ref([])

async function loadFormulas() {
  formulaLoading.value = true
  try {
    formulas.value = await api('/formulas?keyword=' + encodeURIComponent(formulaKw.value))
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    formulaLoading.value = false
  }
}

async function ensureDrugs() {
  if (allDrugs.value.length) return
  const r = await api('/items?active=1&size=500')
  allDrugs.value = r.items
}

function itemPrice(itemId) {
  return allDrugs.value.find(d => d.id === itemId)?.price ?? 0
}

const formulaLinesTotal = computed(() =>
  (formulaForm.value?.lines || [])
    .reduce((s, l) => s + (itemPrice(l.item_id) || 0) * (l.qty || 0), 0),
)

async function openFormula(row) {
  await ensureDrugs()
  formulaForm.value = row
    ? { ...row, lines: row.lines.map(l => ({ item_id: l.item_id, qty: l.qty })) }
    : { id: 0, name: '', price: 0, note: '', active: true, lines: [] }
  formulaDialog.value = true
}

async function saveFormula() {
  const f = formulaForm.value
  if (!f.name || !f.name.trim()) return ElMessage.warning('请填写方名')
  const lines = f.lines.filter(l => l.item_id)
  if (f.id) {
    await saveReq(`/formulas/${f.id}`, { ...f, lines })
  } else {
    await saveReq('/formulas', { ...f, lines })
  }
}

async function saveReq(url, body) {
  formulaSaving.value = true
  try {
    await api(url, { method: body.id ? 'PUT' : 'POST', body })
    ElMessage.success('已保存')
    formulaDialog.value = false
    loadFormulas()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    formulaSaving.value = false
  }
}

async function toggleFormula(row) {
  try {
    await api(`/formulas/${row.id}`, {
      method: 'PUT',
      body: { ...row, active: !row.active, lines: row.lines.map(l => ({ item_id: l.item_id, qty: l.qty })) },
    })
    loadFormulas()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

loadItems()
</script>

<style scoped>
.bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
.fline { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.famount { color: #666; font-size: 13px; width: 72px; text-align: right; }
</style>
