import { ElMessage } from 'element-plus'

/**
 * 复制文本到剪贴板（带降级方案）。
 *
 * navigator.clipboard 仅在安全上下文（HTTPS / localhost）可用，
 * 通过局域网 IP 的 HTTP 访问时为 undefined，必须降级到
 * 隐藏 textarea + document.execCommand('copy')。
 *
 * 返回是否复制成功；失败时统一弹出错误提示。
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  // 1. 原生 Clipboard API（安全上下文）
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      /* 权限被拒等场景，继续走降级 */
    }
  }

  // 2. 降级：隐藏 textarea + execCommand
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}

/** 复制并给出成功/失败提示（业务页面直接调用） */
export async function copyWithToast(text: string, successTip?: string, failTip?: string): Promise<boolean> {
  const ok = await copyToClipboard(text)
  if (ok) {
    if (successTip) ElMessage.success(successTip)
  } else {
    ElMessage.error(failTip || '复制失败，请手动复制')
  }
  return ok
}
