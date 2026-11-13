/**
 * 发票上传的图片预处理。
 *
 * 手机相册取到的图片存在三类问题，都会让后端校验失败或上传失败：
 * 1. 格式不是 JPEG/PNG（iPhone 的 HEIC、安卓的 HEIF/WebP）——后端只认 pdf/jpg/jpeg/png；
 * 2. 体积过大（iPhone 原图常见 3~8MB，接近甚至超过 10MB 上限）；
 * 3. MIME 与扩展名对不上（部分机型返回 application/octet-stream）。
 *
 * 这里统一在浏览器里用 canvas 重编码成 JPEG（顺带等比缩小），
 * 既能把 HEIC 之类变成后端认识的 jpg，也能把大图压到几百 KB，弱网下上传更快。
 */

/** 后端允许的扩展名（与 business_task_service.ALLOWED_FILES 对齐） */
const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']

/** 长边上限：发票文字在 1800px 内仍然清晰，同时体积可控 */
const MAX_EDGE = 1800
/** 小于这个体积的 JPEG/PNG 不需要重编码 */
const SKIP_BYTES = 1.5 * 1024 * 1024
/** JPEG 重编码质量 */
const JPEG_QUALITY = 0.86

const extensionOf = (name: string) => {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

const isPlainImage = (file: File) =>
  file.type === 'image/jpeg' || file.type === 'image/png'

/** 裁掉原扩展名，统一改成 .jpg */
const toJpgName = (name: string) => {
  const base = name.replace(/\.[^./\\]+$/, '') || 'invoice'
  return `${base}.jpg`
}

/** 用 Image 解码（比 createImageBitmap 兼容性更稳，iOS 老版本也支持） */
const loadImage = (file: File) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('image decode failed'))
    }
    img.src = url
  })

/**
 * 把用户选中的文件转成后端可直接接收的文件。
 * - PDF 原样返回；
 * - 小体积 JPEG/PNG 原样返回；
 * - 其余图片（HEIC/WebP/超大图）→ canvas 重编码为 JPEG。
 * 解码失败时返回原文件，交给后端给出明确报错，避免前端静默失败。
 */
export async function normalizeInvoiceFile(file: File): Promise<File> {
  if (!file.type.startsWith('image/')) return file
  if (isPlainImage(file) && file.size <= SKIP_BYTES) return file

  try {
    const img = await loadImage(file)
    const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height))
    const width = Math.max(1, Math.round(img.width * scale))
    const height = Math.max(1, Math.round(img.height * scale))

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    // JPEG 不支持透明通道，先铺白底，避免 PNG 透明区域变黑
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, width, height)
    ctx.drawImage(img, 0, 0, width, height)

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY)
    )
    if (!blob) return file

    // 重编码反而更大（原图本身就是压缩过的小图）时保留原图
    if (blob.size >= file.size && isPlainImage(file)) return file

    return new File([blob], toJpgName(file.name), {
      type: 'image/jpeg',
      lastModified: Date.now()
    })
  } catch {
    return file
  }
}

/** 预处理后仍不在后端白名单内（如无法解码的 heic），前端先拦下给提示 */
export const isSupportedInvoiceFile = (file: File) =>
  ALLOWED_EXTENSIONS.includes(extensionOf(file.name)) ||
  ['application/pdf', 'image/jpeg', 'image/png'].includes(file.type)
