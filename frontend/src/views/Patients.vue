<template>
  <div class="page">
    <header class="topbar">
      <el-button :icon="'Back'" @click="$router.push('/')">返回</el-button>
      <span class="title">信息登记 · 患者档案</span>
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
        <el-table-column prop="created_at" label="建档时间" width="150" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">修改</el-button>
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

onMounted(load)
</script>

<style scoped>
.page { min-height: 100%; display: flex; flex-direction: column; }
.topbar { background: #075e54; color: #fff; padding: 10px 24px; display: flex; align-items: center; gap: 16px; }
.title { font-size: 17px; font-weight: bold; }
.content { padding: 20px 24px; }
.bar { display: flex; gap: 16px; margin-bottom: 14px; }
</style>
