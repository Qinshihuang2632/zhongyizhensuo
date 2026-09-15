<template>
  <div>
    <p class="hint" style="margin-top:0">
      定义保健卡持卡人可享受的项目范围：项目从「字典管理」中挑选，逐项标记
      <b>免费</b> 或 <b>折扣</b>（填折扣百分比，如 80 表示按原价 80% 收取）。仅作权益范围登记，不参与自动计价。
    </p>
    <div class="bar">
      <ItemSelect v-model="pickItemId" style="width:280px" @change="addItem" />
      <span class="hint">选中字典条目即加入下方列表（可重复添加不同项目）</span>
    </div>
    <el-table :data="rows" size="small" border>
      <el-table-column label="项目" min-width="180">
        <template #default="{ row }">{{ itemName(row.item_id) || row.item_id }}</template>
      </el-table-column>
      <el-table-column label="权益方式" width="200">
        <template #default="{ row }">
          <el-radio-group v-model="row.type" size="small">
            <el-radio-button value="free">免费</el-radio-button>
            <el-radio-button value="discount">折扣</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
      <el-table-column label="折扣（%）" width="160">
        <template #default="{ row }">
          <el-input-number v-if="row.type === 'discount'" v-model="row.discount"
            :min="1" :max="99" :step="5" size="small" style="width:120px" />
          <span v-else class="hint">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{ $index }">
          <el-button size="small" type="danger" plain :icon="'Delete'" @click="rows.splice($index, 1)" />
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top:12px">
      <el-button type="primary" :loading="saving" @click="save">保存权益配置</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import ItemSelect from './ItemSelect.vue'

const rows = ref([])
const pickItemId = ref(null)
const allItems = ref([])
const saving = ref(false)

function itemName(id) {
  return allItems.value.find(i => i.id === id)?.name || ''
}

function addItem(item) {
  if (!item) return
  if (rows.value.some(r => r.item_id === item.id)) {
    ElMessage.info('该项目已在列表中')
    return
  }
  rows.value.push({ item_id: item.id, type: 'free', discount: 80 })
  pickItemId.value = null
}

async function save() {
  saving.value = true
  try {
    const items = rows.value.map(r => (
      r.type === 'free' ? { item_id: r.item_id, type: 'free' }
                        : { item_id: r.item_id, type: 'discount', discount: r.discount || 80 }
    ))
    await api('/settings', {
      method: 'PUT',
      body: { values: { card_benefits: JSON.stringify({ items }) } },
    })
    ElMessage.success('权益配置已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function load() {
  allItems.value = (await api('/items?size=500')).items
  const cfg = await api('/settings')
  try {
    const v = JSON.parse(cfg.card_benefits || '{}')
    rows.value = (v.items || []).map(x => ({ ...x, discount: x.discount || 80 }))
  } catch { /* 忽略 */ }
}

onMounted(load)
</script>

<style scoped>
.bar { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }
.hint { color: #909399; font-size: 12px; }
</style>
