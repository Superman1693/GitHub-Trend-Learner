/** 内联 SVG 图标集（避免引入图标库依赖，统一 16px 线性风格）。 */
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Base({ size = 16, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  )
}

export const IconDashboard = (p: IconProps) => (
  <Base {...p}>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </Base>
)

export const IconDocument = (p: IconProps) => (
  <Base {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5M9 13h6M9 17h4" />
  </Base>
)

export const IconTask = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 12h4l3 8 4-16 3 8h4" />
  </Base>
)

export const IconSettings = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 6h16M4 12h16M4 18h16" />
    <circle cx="9" cy="6" r="2" fill="var(--c-surface)" />
    <circle cx="15" cy="12" r="2" fill="var(--c-surface)" />
    <circle cx="8" cy="18" r="2" fill="var(--c-surface)" />
  </Base>
)

export const IconMenu = (p: IconProps) => (
  <Base {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Base>
)

export const IconClose = (p: IconProps) => (
  <Base {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Base>
)

export const IconRefresh = (p: IconProps) => (
  <Base {...p}>
    <path d="M21 12a9 9 0 1 1-3-6.7" />
    <path d="M21 4v5h-5" />
  </Base>
)

export const IconSearch = (p: IconProps) => (
  <Base {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Base>
)

export const IconChevronRight = (p: IconProps) => (
  <Base {...p}>
    <path d="m9 5 7 7-7 7" />
  </Base>
)

export const IconExternal = (p: IconProps) => (
  <Base {...p}>
    <path d="M14 4h6v6M20 4l-8 8" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Base>
)

export const IconAlert = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3 2 20h20L12 3z" />
    <path d="M12 9v5M12 17.5v.5" />
  </Base>
)

export const IconSpark = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
    <circle cx="12" cy="12" r="2.6" />
  </Base>
)

export const IconStar = (p: IconProps) => (
  <Base {...p}>
    <path d="m12 3.6 2.6 5.3 5.8.85-4.2 4.1 1 5.8-5.2-2.75L6.8 19.6l1-5.8-4.2-4.1 5.8-.85z" />
  </Base>
)

export const IconFilter = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 5h18l-7 8v6l-4 2v-8z" />
  </Base>
)

export const IconArrowLeft = (p: IconProps) => (
  <Base {...p}>
    <path d="M19 12H5M12 19l-7-7 7-7" />
  </Base>
)

export const IconLayers = (p: IconProps) => (
  <Base {...p}>
    <path d="m12 3 9 5-9 5-9-5 9-5z" />
    <path d="m3 13 9 5 9-5" />
  </Base>
)

export const IconTag = (p: IconProps) => (
  <Base {...p}>
    <path d="M3 11V4a1 1 0 0 1 1-1h7l9 9-8 8-9-9z" />
    <circle cx="7.5" cy="7.5" r="1.4" />
  </Base>
)

export const IconFlame = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3c1 3-2 4-2 7a3 3 0 0 0 6 0c0-1-.4-1.8-1-2.5.3 2-1.2 3-2 3 .8-2 .2-4-1-7.5z" />
    <path d="M12 21a6 6 0 0 0 6-6c0-2.2-1.1-3.9-2.4-5.2" />
    <path d="M12 21a6 6 0 0 1-6-6c0-1.9.9-3.5 2-4.8" />
  </Base>
)

export const IconDownload = (p: IconProps) => (
  <Base {...p}>
    <path d="M12 3v12" />
    <path d="m7 11 5 5 5-5" />
    <path d="M4 20h16" />
  </Base>
)
