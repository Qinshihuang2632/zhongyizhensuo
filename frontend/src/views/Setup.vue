<template>
  <div class="wrap">
    <el-card class="box">
      <h2>初始化系统</h2>
      <p class="tip">首次使用：请设置管理员密码和诊所名称（之后可在「系统设置」中修改）。</p>
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="诊所名称">
          <el-input v-model="clinicName" placeholder="例如：XX中医诊所" maxlength="50" />
        </el-form-item>
        <el-form-item label="管理密码">
          <el-input v-model="password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="password2" type="password" show-password />
        </el-form-item>
        <el-button type="primary" :loading="busy" style="width:100%" @click="submit">
          完成初始化
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const router = useRouter()
const clinicName = ref('')
const password = ref('')
const password2 = ref('')
const busy = ref(false)

async function submit() {
  if (password.value.length < 6) return ElMessage.warning('密码至少 6 位')
  if (password.value !== password2.value) return ElMessage.warning('两次输入的密码不一致')
  busy.value = true
  try {
    await api('/setup/init', { method: 'POST', body: { password: password.value, clinic_name: clinicName.value } })
    ElMessage.success('初始化完成，请登录')
    router.push('/login')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.wrap { height: 100%; display: flex; align-items: center; justify-content: center; }
.box { width: 420px; }
h2 { margin: 0 0 6px; text-align: center; }
.tip { color: #888; font-size: 13px; margin-bottom: 18px; text-align: center; }
</style>
