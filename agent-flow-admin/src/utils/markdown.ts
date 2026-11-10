import { marked } from 'marked'

// 会话式输出与文档预览共用同一套解析规则：
// 单换行按 <br> 处理（AI 输出常见），GFM 支持表格 / 删除线 / 任务列表
marked.setOptions({ gfm: true, breaks: true, async: false })

/**
 * 基础净化：去掉脚本类标签、内联事件与 javascript: 链接。
 * 文档 md 来自 MinerU 解析产物、AI 内容来自模型输出，做兜底即可。
 */
export const sanitizeMarkdownHtml = (html: string): string =>
  html
    .replace(/<\s*(script|style|iframe|object|embed)[\s\S]*?<\s*\/\s*\1\s*>/gi, '')
    .replace(/<\s*\/?\s*(script|style|iframe|object|embed)[^>]*>/gi, '')
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/(href|src)\s*=\s*("|')\s*javascript\s*:[^"']*\2/gi, '$1="#"')

const htmlCache = new Map<string, string>()

/** markdown → HTML（带缓存，流式输出时同一前缀不会重复解析） */
export const renderMarkdown = (raw: string | null | undefined): string => {
  const text = raw ?? ''
  if (!text) return ''
  const hit = htmlCache.get(text)
  if (hit !== undefined) return hit
  const html = sanitizeMarkdownHtml(marked.parse(text) as string)
  if (htmlCache.size > 300) htmlCache.clear()
  htmlCache.set(text, html)
  return html
}
