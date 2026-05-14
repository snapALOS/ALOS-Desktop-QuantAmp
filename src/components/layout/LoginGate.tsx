import { useEffect, useState } from 'react'
import { api, ApiError } from '@/api'
import { useAuth } from '@/store/auth'
import type { OriginalAdminBootstrapStatus } from '@/types/api'
import logo from '@/assets/logo-alos.svg'

/**
 * First-run login screen. Asks for the bootstrap API key, validates it
 * against POST /auth/validate, and persists it to the auth store on success.
 */
export function LoginGate() {
  const [key, setKey] = useState('')
  const [adminName, setAdminName] = useState('admin')
  const [bootstrapStatus, setBootstrapStatus] =
    useState<OriginalAdminBootstrapStatus | null>(null)
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [creatingAdmin, setCreatingAdmin] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copyStatus, setCopyStatus] = useState<string | null>(null)
  const setApiKey = useAuth((s) => s.setApiKey)
  const setUser = useAuth((s) => s.setUser)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const status = await api.getOriginalAdminBootstrapStatus()
        if (!cancelled) setBootstrapStatus(status)
      } catch {
        if (!cancelled) setBootstrapStatus(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function onCreateOriginalAdmin() {
    setCreatingAdmin(true)
    setError(null)
    setCreatedKey(null)

    try {
      const result = await api.createOriginalAdmin(adminName)
      setKey(result.api_key)
      setCreatedKey(result.api_key)
      setBootstrapStatus((prev) =>
        prev
          ? { ...prev, users_exist: true, active_admins: 1, can_bootstrap: false }
          : prev,
      )
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('Original admin setup has already been completed. Sign in with an existing key.')
      } else if (err instanceof ApiError && err.status === 0) {
        setError('Cannot reach ALOS backend. Is it running on localhost:8000?')
      } else {
        setError((err as Error).message || 'Could not create the original admin.')
      }
    } finally {
      setCreatingAdmin(false)
    }
  }

  async function copyCreatedKey() {
    if (!createdKey) return
    setCopyStatus(null)
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(createdKey)
      } else {
        const textarea = document.createElement('textarea')
        textarea.value = createdKey
        textarea.setAttribute('readonly', 'true')
        textarea.style.position = 'fixed'
        textarea.style.left = '-9999px'
        document.body.appendChild(textarea)
        textarea.select()
        const copied = document.execCommand('copy')
        document.body.removeChild(textarea)
        if (!copied) throw new Error('Clipboard fallback failed')
      }
      setCopyStatus('Copied.')
      window.setTimeout(() => setCopyStatus(null), 2500)
    } catch {
      setError('Could not copy automatically. Select and copy the key manually.')
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = key.trim()
    if (!trimmed) return

    setSubmitting(true)
    setError(null)

    try {
      // Temporarily set the key so the client authorizes the /auth/me probe.
      setApiKey(trimmed)
      const user = await api.me()
      setUser(user)
    } catch (err) {
      setApiKey(null)
      setUser(null)
      if (err instanceof ApiError && err.status === 401) {
        setError('Invalid or expired API key.')
      } else if (err instanceof ApiError && err.status === 0) {
        setError('Cannot reach ALOS backend. Is it running on localhost:8000?')
      } else {
        setError((err as Error).message || 'Authentication failed.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-full w-full items-center justify-center bg-background p-8">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3">
          <img src={logo} alt="ALOS" className="h-10 w-10" />
          <div>
            <h1 className="text-xl font-semibold tracking-tight">ALOS</h1>
          <p className="text-xs text-muted-foreground">Autonomous Local Operating System</p>
          </div>
        </div>

        {bootstrapStatus?.can_bootstrap && (
          <section className="mt-8 rounded-lg border border-primary/40 bg-card p-6 shadow-lg">
            <p className="text-sm font-semibold text-foreground">
              Create the original admin
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              This is a fresh local ALOS install. Create the first admin here;
              no terminal bootstrap is required.
            </p>

            <label className="mt-4 block text-sm font-medium text-foreground">
              Admin name
            </label>
            <input
              type="text"
              autoComplete="username"
              spellCheck={false}
              value={adminName}
              onChange={(e) => setAdminName(e.target.value)}
              className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40"
            />

            <button
              type="button"
              disabled={creatingAdmin || adminName.trim().length === 0}
              onClick={onCreateOriginalAdmin}
              className="mt-4 w-full rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creatingAdmin ? 'Creating admin…' : 'Create original admin'}
            </button>
          </section>
        )}

        <form
          onSubmit={onSubmit}
          className="mt-6 rounded-lg border border-border bg-card p-6 shadow-lg"
        >
          <label className="block text-sm font-medium text-foreground">
            API Key
          </label>
          <p className="mt-1 text-xs text-muted-foreground">
            Paste an existing ALOS key, or create the original admin above on a
            fresh install. Keys are stored locally and only sent to your ALOS
            backend.
          </p>
          <input
            type={createdKey ? 'text' : 'password'}
            autoFocus={!bootstrapStatus?.can_bootstrap}
            autoComplete="off"
            spellCheck={false}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="alos_…"
            className="mt-3 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40"
          />

          {createdKey && (
            <div className="mt-3 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-xs leading-relaxed text-foreground">
              <p className="font-semibold">Original admin key created.</p>
              <p className="mt-1 text-muted-foreground">
                Copy this key now or connect to ALOS so it is saved in this app.
              </p>
              <button
                type="button"
                onClick={copyCreatedKey}
                className="mt-2 rounded-md border border-border bg-background px-2 py-1 font-semibold text-foreground"
              >
                Copy key
              </button>
              {copyStatus && <span className="ml-2 text-[11px] font-semibold text-primary">{copyStatus}</span>}
            </div>
          )}

          {error && (
            <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || key.trim().length === 0}
            className="mt-5 w-full rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Connecting…' : 'Connect'}
          </button>

          {bootstrapStatus && !bootstrapStatus.can_bootstrap && (
            <p className="mt-4 text-[11px] leading-snug text-muted-foreground/70">
              Original admin setup is already complete for this local data
              directory. Use an existing key or an authenticated recovery flow.
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
