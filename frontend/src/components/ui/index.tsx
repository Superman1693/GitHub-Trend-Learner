/**
 * 基础 UI 组件库（无业务语义，可在任意页面复用）。
 * 每个组件保持单一职责，样式由 ui.css 提供。
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './ui.css'

/* ---------------- Button ---------------- */

type ButtonVariant = 'default' | 'primary' | 'ghost' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: 'md' | 'lg'
  block?: boolean
  loading?: boolean
  icon?: ReactNode
}

export function Button({
  variant = 'default',
  size = 'md',
  block = false,
  loading = false,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  const classes = [
    'btn',
    variant !== 'default' ? `btn--${variant}` : '',
    size === 'lg' ? 'btn--lg' : '',
    block ? 'btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button className={classes} disabled={disabled || loading} {...rest}>
      {loading ? <span className="spinner" aria-hidden="true" /> : icon}
      {children}
    </button>
  )
}

/* ---------------- Badge ---------------- */

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'accent' | 'success' | 'warn' | 'danger'
  children: ReactNode
}) {
  return <span className={`badge${tone === 'neutral' ? '' : ` badge--${tone}`}`}>{children}</span>
}

/* ---------------- Card ---------------- */

export function Card({
  title,
  description,
  actions,
  flush = false,
  children,
}: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  flush?: boolean
  children: ReactNode
}) {
  return (
    <section className={`card${flush ? ' card--flush' : ''}`}>
      {(title || actions) && (
        <header className="card__head">
          <div>
            {title && <h2 className="card__title">{title}</h2>}
            {description && <p className="card__desc">{description}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

/* ---------------- Spinner / LoadingBlock ---------------- */

export function Spinner({ large = false }: { large?: boolean }) {
  return <span className={`spinner${large ? ' spinner--lg' : ''}`} aria-hidden="true" />
}

export function LoadingBlock({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="loading-block" role="status" aria-live="polite">
      <Spinner large />
      <span>{text}</span>
    </div>
  )
}

/* ---------------- EmptyState ---------------- */

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="empty">
      <div className="empty__icon" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 6h16M4 12h10M4 18h7" strokeLinecap="round" />
        </svg>
      </div>
      <p className="empty__title">{title}</p>
      {description && <p className="empty__desc">{description}</p>}
      {action}
    </div>
  )
}

/* ---------------- StatusDot ---------------- */

export function StatusDot({ tone = 'idle' }: { tone?: 'ok' | 'warn' | 'err' | 'running' | 'idle' }) {
  return <span className={`dot${tone === 'idle' ? '' : ` dot--${tone}`}`} aria-hidden="true" />
}

/* ---------------- Alert ---------------- */

export function Alert({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'danger'
  title?: string
  children: ReactNode
}) {
  return (
    <div className={`alert alert--${tone}`} role={tone === 'danger' ? 'alert' : undefined}>
      <div>
        {title && <p className="alert__title">{title}</p>}
        <div>{children}</div>
      </div>
    </div>
  )
}

/* ---------------- Field ---------------- */

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string
  hint?: string
  htmlFor?: string
  children: ReactNode
}) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint && <span className="field__hint">{hint}</span>}
    </div>
  )
}
