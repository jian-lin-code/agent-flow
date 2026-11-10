<template>
  <el-config-provider :locale="elementLocale">
    <router-view />
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import enUs from 'element-plus/es/locale/lang/en'

const { locale } = useI18n()

// Element Plus 内置文案（分页、日期选择等）跟随当前语言
const elementLocale = computed(() => (locale.value === 'en-US' ? enUs : zhCn))
</script>
