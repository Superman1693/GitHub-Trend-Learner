/** 响应式断点 Hook：JS 侧与 CSS 媒体查询保持同一套断点语义。 */
import { useEffect, useState } from 'react'

export const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
} as const

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === 'undefined' ? false : window.matchMedia(query).matches,
  )

  useEffect(() => {
    const mql = window.matchMedia(query)
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches)
    setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}

/** 是否为移动端（< md）。用于切换侧栏抽屉与底部导航。 */
export function useIsMobile(): boolean {
  return useMediaQuery(`(max-width: ${BREAKPOINTS.md - 1}px)`)
}

/** 是否为紧凑桌面（< lg）。用于收敛内边距与隐藏次要列。 */
export function useIsCompact(): boolean {
  return useMediaQuery(`(max-width: ${BREAKPOINTS.lg - 1}px)`)
}
