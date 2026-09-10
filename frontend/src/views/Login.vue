<template>
  <div class="wrap">
    <el-card class="box">
      <h2>{{ clinicName || '中医诊所管理系统' }}</h2>
      <p class="tip">请输入管理员密码登录</p>
      <el-input
        v-model="password"
        type="password"
        show-password
        size="large"
        placeholder="管理密码"
        @keyup.enter="submit"
      />
      <el-button type="primary" size="large" :loading="busy" style="width:100%;margin-top:16px" @click="submit">
        登 录
      </el-button>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, setToken } from '../api'

const router = useRouter()
const clinicName = ref('')
const password = ref('')
const busy = ref(false)

onMounted(async () => {
  try {
    const s = await api('/setup/status')
    clinicName.value = s.clinic_name
  } catch { /* 忽略，显示默认名 */ }
})

async function submit() {
  if (!password.value) return ElMessage.warning('请输入密码')
  busy.value = true
  try {
    const { token } = await api('/auth/login', { method: 'POST', body: { username: 'admin', password: password.value } })
    setToken(token)
    router.push('/')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.wrap { height: 100%; display: flex; align-items: center; justify-content: center; }
.box { width: 400px; }
h2 { margin: 0 0 6px; text-align: center; }
.tip { color: #888; font-size: 13px; margin-bottom: 16px; text-align: center; }
</style>
