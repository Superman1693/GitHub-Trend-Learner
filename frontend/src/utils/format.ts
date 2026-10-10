/** 通用格式化工具。 */

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** 从文件名推导可读标题（去掉扩展名、下划线转斜杠）。 */
export function prettifyName(name: string): string {
  return name.replace(/\.md$/i, '').replace(/_/g, '/')
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 19)
}

/** 大数字缩写：12345 → 12.3k，1234567 → 1.2M */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '0'
  if (value < 1000) return String(value)
  if (value < 1_000_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)}k`
  return `${(value / 1_000_000).toFixed(1)}M`
}

/** 生成用于锚点跳转的稳定 id。 */
export function slugify(input: string, fallback: string): string {
  const slug = input
    .trim()
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || fallback
}

/** 中文章节序号（用于目录左侧编号）。 */
export const CN_INDEX = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

export function cnIndex(i: number): string {
  return CN_INDEX[i] ?? String(i + 1)
}
