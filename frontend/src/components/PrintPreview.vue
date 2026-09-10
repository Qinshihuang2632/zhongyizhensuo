<template>
  <el-dialog
    :model-value="visible"
    title="打印预览（A4）"
    width="82%"
    top="3vh"
    destroy-on-close
    @update:model-value="v => $emit('update:visible', v)"
  >
    <iframe ref="frame" :srcdoc="html" class="print-frame"></iframe>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" :icon="'Printer'" @click="doPrint">打印</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  visible: { type: Boolean, default: false },
  html: { type: String, default: '' },
})
defineEmits(['update:visible'])

const frame = ref(null)

function doPrint() {
  const win = frame.value?.contentWindow
  if (win) {
    win.focus()
    win.print()
  }
}
</script>

<style scoped>
.print-frame { width: 100%; height: 70vh; border: 1px solid #ddd; background: #fff; }
</style>
