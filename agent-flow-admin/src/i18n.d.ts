// vue-i18n 全局类型：让模板中的 $t / $tc / $d 等通过 TypeScript 检查
import type { Composer } from 'vue-i18n'

declare module 'vue' {
  export interface ComponentCustomProperties {
    $t: Composer['t']
    $te: Composer['te']
    $d: Composer['d']
    $n: Composer['n']
    $tm: Composer['tm']
  }
}

export {}
