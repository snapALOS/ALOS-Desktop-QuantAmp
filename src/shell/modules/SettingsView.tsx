import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  Loader2,
  RotateCcw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react'
import { api, ApiError } from '@/api'
import { PROVIDERS, providerById } from '@/components/setup/providers'
import type {
  AppSettings,
  AutonomousWriteMode,
  OriginalAdminBootstrapStatus,
  ProviderConfigPayload,
  ProviderId,
  ProviderValidationResult,
  User,
} from '@/types/api'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

interface SettingsForm {
  llm_provider: ProviderId
  api_key: string
  model_name: string
  base_url: string
  max_retries: string
  timeout_seconds: string
  temperature: string
  top_p: string
  top_k: string
  max_output_tokens: string
  context_window_tokens: string
  max_input_tokens: string
  reserved_context_tokens: string
  presence_penalty: string
  frequency_penalty: string
  seed: string
  max_agent_turns: string
  chamber_gate_required: boolean
  allow_chamber_override: boolean
  autonomous_write_mode: AutonomousWriteMode
}

const DEFAULT_FORM: SettingsForm = {
  llm_provider: 'nvidia',
  api_key: '',
  model_name: 'nvidia/nemotron-3-super-120b-a12b',
  base_url: 'https://integrate.api.nvidia.com/v1',
  max_retries: '3',
  timeout_seconds: '120',
  temperature: '0.2',
  top_p: '1',
  top_k: '',
  max_output_tokens: '4096',
  context_window_tokens: '128000',
  max_input_tokens: '',
  reserved_context_tokens: '4096',
  presence_penalty: '0',
  frequency_penalty: '0',
  seed: '',
  max_agent_turns: '250',
  chamber_gate_required: true,
  allow_chamber_override: true,
  autonomous_write_mode: 'chamber_gated',
}

export function SettingsView() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [form, setForm] = useState<SettingsForm>(DEFAULT_FORM)
  const [user, setUser] = useState<User | null>(null)
  const [bootstrap, setBootstrap] = useState<OriginalAdminBootstrapStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [validating, setValidating] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [validation, setValidation] = useState<ProviderValidationResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const provider = useMemo(() => providerById(form.llm_provider), [form.llm_provider])
  const dirty = settings ? JSON.stringify(formWithoutKey(form)) !== JSON.stringify(formFromSettings(settings)) : false

  useEffect(() => {
    void refresh()
  }, [])

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const [nextSettings, nextUser, nextBootstrap] = await Promise.all([
        api.getSettings(),
        api.me().catch(() => null),
        api.getOriginalAdminBootstrapStatus().catch(() => null),
      ])
      setSettings(nextSettings)
      setForm(formFromSettings(nextSettings))
      setUser(nextUser)
      setBootstrap(nextBootstrap)
    } catch (err) {
      setError(formatError(err))
    } finally {
      setLoading(false)
    }
  }

  function setField<K extends keyof SettingsForm>(key: K, value: SettingsForm[K]) {
    setForm((current) => ({ ...current, [key]: value }))
    setSaveState('idle')
  }

  function selectProvider(id: ProviderId) {
    const def = providerById(id)
    setForm((current) => ({
      ...current,
      llm_provider: id,
      model_name: current.model_name || def.defaultModel,
      base_url: def.defaultBaseUrl,
      api_key: '',
    }))
    setValidation(null)
    setSaveState('idle')
  }

  async function validateProvider() {
    setValidating(true)
    setValidation(null)
    setError(null)
    try {
      setValidation(await api.validateProvider(buildPayload(form)))
    } catch (err) {
      setValidation({
        ok: false,
        provider: form.llm_provider,
        model: form.model_name,
        base_url: form.base_url,
        api_key_set: Boolean(form.api_key || settings?.api_key_set),
        message: formatError(err),
      })
    } finally {
      setValidating(false)
    }
  }

  async function saveSettings() {
    setSaveState('saving')
    setError(null)
    try {
      const next = await api.saveProviderConfig(buildPayload(form))
      setSettings(next)
      setForm(formFromSettings(next))
      setSaveState('saved')
    } catch (err) {
      setError(formatError(err))
      setSaveState('error')
    }
  }

  async function clearProvider() {
    setSaveState('saving')
    setError(null)
    try {
      const next = await api.clearProviderSettings()
      setSettings(next)
      setForm(formFromSettings(next))
      setValidation(null)
      setSaveState('saved')
    } catch (err) {
      setError(formatError(err))
      setSaveState('error')
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-background text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading settings...
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto bg-background">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-6">
        <header className="flex flex-col gap-3 border-b border-border pb-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">System preferences</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">Settings</h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Tune model behavior, provider credentials, write safety, and local diagnostics.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setForm(settings ? formFromSettings(settings) : DEFAULT_FORM)}
              disabled={!dirty || saveState === 'saving'}
              className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw className="h-4 w-4" />
              Cancel
            </button>
            <button
              type="button"
              onClick={saveSettings}
              disabled={saveState === 'saving'}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saveState === 'saving' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save settings
            </button>
          </div>
        </header>

        {error && (
          <Notice tone="error" icon={<AlertTriangle className="h-4 w-4" />}>
            {error}
          </Notice>
        )}
        {saveState === 'saved' && (
          <Notice tone="success" icon={<CheckCircle2 className="h-4 w-4" />}>
            Settings saved. New model calls and patch writes will use this configuration.
          </Notice>
        )}

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
          <div className="flex flex-col gap-6">
            <SettingsPanel
              icon={<KeyRound className="h-4 w-4" />}
              title="Provider"
              description="Credentials stay local. Leave the key blank to keep the current saved key."
            >
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-sm">
                  <span className="mb-1 block font-medium">Provider</span>
                  <select
                    value={form.llm_provider}
                    onChange={(event) => selectProvider(event.target.value as ProviderId)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2"
                  >
                    {PROVIDERS.map((item) => (
                      <option key={item.id} value={item.id}>{item.label}</option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">
                  <span className="mb-1 block font-medium">Model</span>
                  <input
                    value={form.model_name}
                    onChange={(event) => setField('model_name', event.target.value)}
                    placeholder={provider.defaultModel || 'provider/model'}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="mb-1 block font-medium">API key</span>
                  <input
                    value={form.api_key}
                    onChange={(event) => setField('api_key', event.target.value)}
                    type="password"
                    placeholder={settings?.api_key_set ? 'Saved key will be kept' : provider.requiresApiKey ? 'Required' : 'Not required'}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2"
                  />
                </label>
                <label className="text-sm">
                  <span className="mb-1 block font-medium">Base URL</span>
                  <input
                    value={form.base_url}
                    onChange={(event) => setField('base_url', event.target.value)}
                    disabled={!provider.baseUrlOverridable}
                    placeholder={provider.defaultBaseUrl || 'SDK default'}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 disabled:opacity-60"
                  />
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-2 pt-2">
                <button
                  type="button"
                  onClick={validateProvider}
                  disabled={validating}
                  className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50"
                >
                  {validating ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  Validate provider
                </button>
                <button
                  type="button"
                  onClick={clearProvider}
                  disabled={saveState === 'saving'}
                  className="inline-flex items-center gap-2 rounded-lg border border-destructive/40 px-3 py-2 text-sm text-destructive hover:bg-destructive/10 disabled:opacity-50"
                >
                  Clear provider
                </button>
                <StatusPill ok={settings?.configured ?? false} text={settings?.configured ? 'Configured' : 'Needs setup'} />
              </div>
              {validation && (
                <Notice tone={validation.ok ? 'success' : 'error'} icon={validation.ok ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}>
                  {validation.message || (validation.ok ? 'Provider accepted the configuration.' : validation.errors?.join(' ') || 'Provider validation failed.')}
                </Notice>
              )}
            </SettingsPanel>

            <SettingsPanel
              icon={<SlidersHorizontal className="h-4 w-4" />}
              title="Model Behavior"
              description="Control sampling, response length, and context budget for Chat, Forge, Current, and agents."
            >
              <div className="grid gap-4 md:grid-cols-3">
                <NumberField label="Temperature" value={form.temperature} min="0" max="2" step="0.05" onChange={(value) => setField('temperature', value)} />
                <NumberField label="Top p" value={form.top_p} min="0.01" max="1" step="0.01" onChange={(value) => setField('top_p', value)} />
                <NumberField label="Top k" value={form.top_k} min="1" step="1" placeholder="Provider default" onChange={(value) => setField('top_k', value)} />
                <NumberField label="Max output tokens" value={form.max_output_tokens} min="1" step="1" onChange={(value) => setField('max_output_tokens', value)} />
                <NumberField label="Context window tokens" value={form.context_window_tokens} min="1" step="1" onChange={(value) => setField('context_window_tokens', value)} />
                <NumberField label="Max input tokens" value={form.max_input_tokens} min="1" step="1" placeholder="Auto" onChange={(value) => setField('max_input_tokens', value)} />
                <NumberField label="Reserved context tokens" value={form.reserved_context_tokens} min="1" step="1" onChange={(value) => setField('reserved_context_tokens', value)} />
                <NumberField label="Presence penalty" value={form.presence_penalty} min="-2" max="2" step="0.1" onChange={(value) => setField('presence_penalty', value)} />
                <NumberField label="Frequency penalty" value={form.frequency_penalty} min="-2" max="2" step="0.1" onChange={(value) => setField('frequency_penalty', value)} />
                <NumberField label="Seed" value={form.seed} min="1" step="1" placeholder="Off" onChange={(value) => setField('seed', value)} />
                <NumberField label="Retries" value={form.max_retries} min="1" step="1" onChange={(value) => setField('max_retries', value)} />
                <NumberField label="Timeout seconds" value={form.timeout_seconds} min="1" step="1" onChange={(value) => setField('timeout_seconds', value)} />
              </div>
            </SettingsPanel>

            <SettingsPanel
              icon={<ShieldCheck className="h-4 w-4" />}
              title="Agent And Chamber Safety"
              description="Choose how autonomous work moves from proposed changes to real files."
            >
              <div className="grid gap-4 md:grid-cols-2">
                <div className="md:col-span-2">
                  <NumberField
                    label="Max agent turns"
                    value={form.max_agent_turns}
                    min="1"
                    step="10"
                    onChange={(value) => setField('max_agent_turns', value)}
                  />
                  <p className="mt-1 text-xs text-muted-foreground">
                    How many orchestration cycles an agent run may execute before being halted. Set as high as you need — 500, 800, or more for large multi-step tasks. Default: 250.
                  </p>
                </div>
                <ToggleRow
                  title="Require Chamber before writes"
                  detail="Patch writes must pass build/test evidence before touching the workspace."
                  checked={form.chamber_gate_required}
                  onChange={(value) => setField('chamber_gate_required', value)}
                />
                <ToggleRow
                  title="Allow Chamber override"
                  detail="Authenticated users may apply a blocked patch when they accept the risk."
                  checked={form.allow_chamber_override}
                  onChange={(value) => setField('allow_chamber_override', value)}
                />
                <label className="text-sm md:col-span-2">
                  <span className="mb-1 block font-medium">Autonomous write mode</span>
                  <select
                    value={form.autonomous_write_mode}
                    onChange={(event) => setField('autonomous_write_mode', event.target.value as AutonomousWriteMode)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2"
                  >
                    <option value="manual_only">Manual only</option>
                    <option value="propose_only">Propose only</option>
                    <option value="chamber_gated">Chamber gated</option>
                    <option value="autonomous">Autonomous</option>
                  </select>
                </label>
              </div>
            </SettingsPanel>
          </div>

          <aside className="flex flex-col gap-6">
            <SettingsPanel title="Admin" description="Local account and recovery state.">
              <InfoRow label="Signed in as" value={user ? `${user.username} (${user.role})` : 'Unavailable'} />
              <InfoRow label="Original admin" value={bootstrap?.users_exist ? 'Configured' : 'Not created'} />
              <InfoRow label="Active admins" value={String(bootstrap?.active_admins ?? 'Unknown')} />
              <InfoRow label="First-run bootstrap" value={bootstrap?.can_bootstrap ? 'Available' : 'Closed'} />
            </SettingsPanel>

            <SettingsPanel title="Diagnostics" description="Paths and status for support, recovery, and packaging checks.">
              <InfoRow label="Backend" value={settings?.diagnostics?.status || 'unknown'} />
              <InfoRow label="Version" value={settings?.diagnostics?.version || 'unknown'} />
              <InfoRow label="Data" value={settings?.diagnostics?.data_dir || 'unknown'} />
              <InfoRow label="Logs" value={settings?.diagnostics?.logs_dir || 'unknown'} />
              <InfoRow label="Config" value={settings?.diagnostics?.env_path || 'unknown'} />
              <InfoRow label="Backend dir" value={settings?.diagnostics?.backend_dir || 'unknown'} />
            </SettingsPanel>
          </aside>
        </section>
      </div>
    </div>
  )
}

function SettingsPanel({
  title,
  description,
  icon,
  children,
}: {
  title: string
  description: string
  icon?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-start gap-3">
        {icon && <div className="mt-0.5 text-primary">{icon}</div>}
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  )
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  min?: string
  max?: string
  step?: string
  placeholder?: string
}) {
  return (
    <label className="text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        type="number"
        min={min}
        max={max}
        step={step}
        placeholder={placeholder}
        className="w-full rounded-lg border border-input bg-background px-3 py-2"
      />
    </label>
  )
}

function ToggleRow({
  title,
  detail,
  checked,
  onChange,
}: {
  title: string
  detail: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-4 w-4"
      />
      <span>
        <span className="block text-sm font-medium">{title}</span>
        <span className="mt-1 block text-xs text-muted-foreground">{detail}</span>
      </span>
    </label>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-border pb-3 last:border-0 last:pb-0">
      <dt className="text-xs font-medium uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-mono text-xs text-foreground">{value}</dd>
    </div>
  )
}

function Notice({
  tone,
  icon,
  children,
}: {
  tone: 'success' | 'error'
  icon: ReactNode
  children: ReactNode
}) {
  const classes = tone === 'success'
    ? 'border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300'
    : 'border-destructive/30 bg-destructive/10 text-destructive'
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${classes}`}>
      <span className="mt-0.5">{icon}</span>
      <span>{children}</span>
    </div>
  )
}

function StatusPill({ ok, text }: { ok: boolean; text: string }) {
  return (
    <span className={`rounded-lg border px-2 py-1 text-xs ${ok ? 'border-emerald-600/40 text-emerald-700 dark:text-emerald-300' : 'border-amber-600/40 text-amber-700 dark:text-amber-300'}`}>
      {text}
    </span>
  )
}

function formFromSettings(settings: AppSettings): SettingsForm {
  return {
    llm_provider: settings.llm_provider,
    api_key: '',
    model_name: settings.model_name,
    base_url: settings.base_url || providerById(settings.llm_provider).defaultBaseUrl,
    max_retries: String(settings.max_retries),
    timeout_seconds: String(settings.timeout_seconds),
    temperature: String(settings.temperature),
    top_p: String(settings.top_p),
    top_k: settings.top_k ? String(settings.top_k) : '',
    max_output_tokens: String(settings.max_output_tokens),
    context_window_tokens: String(settings.context_window_tokens),
    max_input_tokens: settings.max_input_tokens ? String(settings.max_input_tokens) : '',
    reserved_context_tokens: String(settings.reserved_context_tokens),
    presence_penalty: String(settings.presence_penalty),
    frequency_penalty: String(settings.frequency_penalty),
    seed: settings.seed ? String(settings.seed) : '',
    max_agent_turns: String(settings.max_agent_turns ?? 250),
    chamber_gate_required: settings.chamber_gate_required,
    allow_chamber_override: settings.allow_chamber_override,
    autonomous_write_mode: settings.autonomous_write_mode,
  }
}

function formWithoutKey(form: SettingsForm) {
  return { ...form, api_key: '' }
}

function buildPayload(form: SettingsForm): ProviderConfigPayload {
  return {
    llm_provider: form.llm_provider,
    api_key: form.api_key.trim() || undefined,
    model_name: form.model_name.trim(),
    base_url: form.base_url.trim() || undefined,
    max_retries: intValue(form.max_retries),
    timeout_seconds: intValue(form.timeout_seconds),
    temperature: floatValue(form.temperature),
    top_p: floatValue(form.top_p),
    top_k: optionalInt(form.top_k),
    max_output_tokens: intValue(form.max_output_tokens),
    context_window_tokens: intValue(form.context_window_tokens),
    max_input_tokens: optionalInt(form.max_input_tokens),
    reserved_context_tokens: intValue(form.reserved_context_tokens),
    presence_penalty: floatValue(form.presence_penalty),
    frequency_penalty: floatValue(form.frequency_penalty),
    seed: optionalInt(form.seed),
    max_agent_turns: intValue(form.max_agent_turns),
    chamber_gate_required: form.chamber_gate_required,
    allow_chamber_override: form.allow_chamber_override,
    autonomous_write_mode: form.autonomous_write_mode,
  }
}

function intValue(value: string) {
  return Number.parseInt(value, 10)
}

function floatValue(value: string) {
  return Number.parseFloat(value)
}

function optionalInt(value: string) {
  const trimmed = value.trim()
  return trimmed ? Number.parseInt(trimmed, 10) : null
}

function formatError(err: unknown) {
  if (err instanceof ApiError && err.body && typeof err.body === 'object' && 'detail' in err.body) {
    const detail = (err.body as { detail: unknown }).detail
    if (detail && typeof detail === 'object' && 'errors' in detail) {
      const errors = (detail as { errors: unknown }).errors
      if (Array.isArray(errors)) return errors.join(' ')
    }
  }
  return err instanceof Error ? err.message : 'Settings request failed.'
}
