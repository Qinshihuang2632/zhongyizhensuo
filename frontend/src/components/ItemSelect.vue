<template>
  <el-select
    :model-value="modelValue"
    filterable
    clearable
    placeholder="输入名称搜索"
    style="width:100%"
    @update:model-value="onChange"
  >
    <el-option
      v-for="o in options"
      :key="o.id"
      :label="`${o.name}（${o.price.toFixed(2)}元/${o.unit || '无单位'}）`"
      :value="o.id"
    />
  </el-select>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  modelValue: { type: Number, default: null },
  categories: { type: Array, default: null },
})
const emit = defineEmits(['update:modelValue', 'change'])
const options = ref([])

onMounted(async () => {
  try {
    const r = await api('/items?active=1&size=500')
    options.value = props.categories
      ? r.items.filter(i => props.categories.includes(i.category))
      : r.items
  } catch { /* 登录超时等情况由全局处理 */ }
})

function onChange(id) {
  emit('update:modelValue', id)
  emit('change', options.value.find(o => o.id === id) || null)
}
</script>
