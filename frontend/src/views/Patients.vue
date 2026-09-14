<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">患者信息 · 患者档案</span>
      <span style="width:76px"></span>
    </header>

    <main class="content">
      <div class="bar">
        <el-input
          v-model="keyword"
          placeholder="搜索：姓名 / 电话 / 编号"
          clearable
          style="width:280px"
          @keyup.enter="search"
          @clear="search"
        >
          <template #append>
            <el-button :icon="'Search'" @click="search" />
          </template>
        </el-input>
        <el-button type="primary" :icon="'Plus'" @click="openAdd">新增患者</el-button>
      </div>

      <el-table :data="items" v-loading="loading" size="small" border>
        <el-table-column prop="no" label="编号" width="80" />
        <el-table-column prop="name" label="姓名" width="110" />
        <el-table-column prop="gender" label="性别" width="60" />
        <el-table-column label="年龄" width="60">
          <template #default="{ row }">{{ ageOf(row.birth_date) || row.age || '' }}</template>
        </el-table-column>
        <el-table-column prop="phone" label="电话" width="130" />
        <el-table-column prop="address" label="地址" min-width="140" show-overflow-tooltip />
        <el-table-column prop="allergy_history" label="过敏史" min-width="110" show-overflow-tooltip />
        <el-table-column label="保健卡" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.has_card" type="success" size="small">有</el-tag>
            <el-tag v-else type="info" size="small">无</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="建档时间" width="150" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">修改</el-button>
            <el-button size="small" @click="openCard(row)">保健卡</el-button>
            <el-button size="small" type="primary" plain :icon="'Printer'" @click="printOne(row)">打印</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        style="margin-top:14px;justify-content:flex-end"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="size"
        :current-page="page"
        @current-change="p => { page = p; load() }"
      />
    </main>

    <!-- 新增 / 修改 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '修改患者' : '新增患者'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="姓名" prop="name"><el-input v-model="form.name" maxlength="50" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="电话" prop="phone"><el-input v-model="form.phone" maxlength="20" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="性别" prop="gender">
              <el-radio-group v-model="form.gender">
                <el-radio value="男">男</el-radio>
                <el-radio value="女">女</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="年龄" prop="age">
              <el-input-number v-model="form.age" :min="1" :max="130" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="出生日期">
          <el-date-picker v-model="form.birth_date" type="date" value-format="YYYY-MM-DD" placeholder="选填" style="width:100%" />
        </el-form-item>
        <el-form-item label="地址"><el-input v-model="form.address" maxlength="100" /></el-form-item>
        <el-form-item label="过敏史"><el-input v-model="form.allergy_history" type="textarea" :rows="2" maxlength="500" /></el-form-item>
        <el-form-item label="既往史"><el-input v-model="form.medical_history" type="textarea" :rows="2" maxlength="500" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="2" maxlength="500" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <PrintPreview v-model:visible="printVisible" :html="printHtml" />

    <!-- 保健卡管理 -->
    <el-dialog v-model="cardVisible" :title="`保健卡 · ${cardRow?.name || ''}`" width="680px">
      <div v-if="cardInfo">
        <div v-if="!cardInfo.has_card" class="card-none">
          <p>该患者暂无保健卡。</p>
          <el-button type="primary" @click="grantCard">授予保健卡（自今日起算权益）</el-button>
        </div>
        <template v-else>
          <p class="card-since">
            获卡日期：<b>{{ cardInfo.since }}</b>
            <span class="rule">权益窗口自获卡后第 61 天起，每 180 天一轮（30 天），期内可任选连续 7 天使用。</span>
          </p>
          <el-table :data="cardInfo.windows" size="small" border max-height="400">
            <el-table-column label="轮次" width="64">
              <template #default="{ row }">第 {{ row.index }} 轮</template>
            </el-table-column>
            <el-table-column label="权益窗口" width="190">
              <template #default="{ row }">{{ row.start }} ~ {{ row.end }}</template>
            </el-table-column>
            <el-table-column label="状态" width="150">
              <template #default="{ row }">
                <el-tag size="small" :type="statusTag(row.status)">{{ row.status }}</el-tag>
                <div v-if="row.status === '未生效'" class="sub">{{ row.days_to_start }} 天后生效 · 提醒{{ row.remind_confirmed ? '已确认' : '待确认' }}</div>
                <div v-if="row.status === '已使用'" class="sub">{{ row.usage_start }} ~ {{ row.usage_end }}</div>
              </template>
            </el-table-column>
            <el-table-column label="开始使用（即日起 7 天）" min-width="230">
              <template #default="{ row }">
                <template v-if="row.status === '可使用'">
                  <el-date-picker
                    v-model="row.startDate"
                    type="date"
                    value-format="YYYY-MM-DD"
                    :disabled-date="(d) => disableUsageDate(d, row)"
                    placeholder="选择开始日"
                    size="small"
                    style="width:140px"
                  />
                  <el-button size="small" type="primary" @click="startUsage(row)">开始使用</el-button>
                </template>
                <span v-else-if="row.status === '已过期'" class="sub">该轮未使用，已失效</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import PrintPreview from '../components/PrintPreview.vue'

const items = ref([])
const total = ref(0)
const page = ref(1)
const size = 20
const keyword = ref('')
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)
const printVisible = ref(false)
const printHtml = ref('')

const emptyForm = () => ({
  id: 0, name: '', gender: '', age: null, birth_date: '', phone: '',
  address: '', allergy_history: '', medical_history: '', note: '',
})
const form = reactive(emptyForm())

const rules = {
  name: [{ required: true, message: '请填写姓名', trigger: 'blur' }],
  gender: [{ required: true, message: '请选择性别', trigger: 'change' }],
  age: [{ required: true, message: '请填写年龄', trigger: 'blur' }],
  phone: [{ required: true, message: '请填写电话', trigger: 'blur' }],
}

function ageOf(birth) {
  if (!birth) return ''
  const b = new Date(birth)
  if (isNaN(b.getTime())) return ''
  const t = new Date()
  let a = t.getFullYear() - b.getFullYear()
  const m = t.getMonth() - b.getMonth()
  if (m < 0 || (m === 0 && t.getDate() < b.getDate())) a--
  return a >= 0 && a < 130 ? a : ''
}

async function load() {
  loading.value = true
  try {
    const r = await api(`/patients?keyword=${encodeURIComponent(keyword.value)}&page=${page.value}&size=${size}`)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function openAdd() {
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, emptyForm(), row)
  dialogVisible.value = true
}

async function save() {
  await formRef.value.validate().catch(() => Promise.reject())
  saving.value = true
  try {
    const { id, ...body } = form
    if (id) await api(`/patients/${id}`, { method: 'PUT', body })
    else await api('/patients', { method: 'POST', body })
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function printOne(row) {
  try {
    const p = await api(`/patients/${row.id}`)
    const { html } = await api('/print/preview', {
      method: 'POST',
      body: {
        template: 'patient_info',
        data: { p: { ...p, age: ageOf(p.birth_date) || p.age } },
      },
    })
    printHtml.value = html
    printVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---- 保健卡 ----
const cardVisible = ref(false)
const cardRow = ref(null)
const cardInfo = ref(null)

async function openCard(row) {
  cardRow.value = row
  cardInfo.value = null
  cardVisible.value = true
  await loadCard()
}

async function loadCard() {
  cardInfo.value = await api(`/cards/${cardRow.value.id}`)
  // 未生效窗口的"开始使用"日期默认为窗口首日（可改为窗口内任意连续7天的起点）
  for (const w of cardInfo.value.windows || []) {
    if (w.status === '可使用' && !w.startDate) {
      const today = new Date().toISOString().slice(0, 10)
      w.startDate = today >= w.start && addDays(today, 6) <= w.end ? today : w.start
    }
  }
}

function addDays(dateStr, n) {
  const d = new Date(dateStr)
  d.setDate(d.getDate() + n)
  return d.toISOString().slice(0, 10)
}

function disableUsageDate(d, row) {
  const s = d.toISOString().slice(0, 10)
  return s < row.start || addDays(s, 6) > row.end
}

function statusTag(s) {
  return { 已使用: 'success', 可使用: 'warning', 未生效: 'info', 已过期: 'danger' }[s] || 'info'
}

async function grantCard() {
  try {
    await api(`/cards/${cardRow.value.id}/grant`, { method: 'POST', body: {} })
    ElMessage.success('已授予保健卡')
    await loadCard()
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function startUsage(row) {
  if (!row.startDate) return ElMessage.warning('请选择开始日期')
  try {
    const r = await api(`/cards/${cardRow.value.id}/start`, {
      method: 'POST',
      body: { window_index: row.index, start_date: row.startDate },
    })
    ElMessage.success(`权益已开始：${r.start} ~ ${r.end}`)
    await loadCard()
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
.card-none { text-align: center; padding: 10px 0; }
.card-since { margin-top: 0; }
.card-since .rule { display: block; color: #909399; font-size: 12px; margin-top: 4px; }
.sub { color: #909399; font-size: 12px; margin-top: 2px; }
</style>
