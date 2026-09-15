<template>
  <div>
    <div class="bar">
      <el-input v-model="newName" placeholder="新增病情标签，如：颈椎病" maxlength="30" style="width:240px"
        @keyup.enter="add" />
      <el-button type="primary" :icon="'Plus'" :loading="saving" @click="add">添加标签</el-button>
      <span class="hint">患者建档时从这里多选「病情」；统计（汇总/保健卡使用）按这些标签分类。</span>
    </div>
    <el-table :data="tags" size="small" border max-height="430">
      <el-table-column prop="name" label="标签名" min-width="160" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.active ? 'success' : 'info'" size="small">{{ row.active ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" @click="rename(row)">改名</el-button>
          <el-button size="small" :type="row.active ? 'warning' : 'success'" plain @click="toggle(row)">
            {{ row.active ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <p class="hint" style="margin-top:8px">停用的标签不再出现在患者建档选项中，但历史数据与统计不受影响。</p>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const tags = ref([])
const newName = ref('')
const saving = ref(false)

async function load() {
  tags.value = await api('/conditions')
}

async function add() {
  if (!newName.value.trim()) return ElMessage.warning('请输入标签名')
  saving.value = true
  try {
    await api('/conditions', { method: 'POST', body: { name: newName.value } })
    newName.value = ''
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function rename(row) {
  try {
    const { value } = await ElMessageBox.prompt('修改标签名', '改名', {
      inputValue: row.name, inputPattern: /\S+/, inputErrorMessage: '标签名不能为空',
    })
    await api(`/conditions/${row.id}`, { method: 'PUT', body: { name: value } })
    load()
  } catch { /* 取消 */ }
}

async function toggle(row) {
  try {
    await api(`/conditions/${row.id}/toggle`, { method: 'POST' })
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.bar { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
</style>
