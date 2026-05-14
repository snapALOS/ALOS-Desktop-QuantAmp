import { useMemo, useState } from 'react'
import { CheckCircle2, ChevronRight, Loader2, XCircle } from 'lucide-react'
import { api, ApiError } from '@/api'
import { cn } from '@/lib/utils'
import logo from '@/assets/logo-alos.svg'
import type {
  ProviderConfigPayload,
  ProviderId,
  ProviderValidationResult,
} from '@/types/api'
import { PROVIDERS, providerById } from './providers'

type Step = 'provider' | 'credentials' | 'validate' | 'done'

interface Props {
  /** Called once provider config has been validated AND persisted. */
  onComplete: () => void
}

export function SetupWizard({ onComplete }: Props) {
  const [step, setStep] = useState<Step>('provider')
  const [providerId, setProviderId] = useState<ProviderId>('nvidia')
  const provider = useMemo(() => providerById(providerId), [providerId])

  // Credential form state — re-seeded whenever the provider changes.
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(provider.defaultModel)
  const [baseUrl, setBaseUrl] = useState(provider.defaultBaseUrl)

  const [validating, setValidating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<ProviderValidationResult | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  function selectProvider(id: ProviderId) {
    setProviderId(id)
    const def = providerById(id)
    setApiKey('')
    setModel(def.defaultModel)
    setBaseUrl(def.defaultBaseUrl)
    setResult(null)
    setFormError(null)
    setStep('credentials')
  }

  function payload(): ProviderConfigPayload {
    return {
      llm_provider: providerId,
      api_key: apiKey.trim(),
      model_name: model.trim(),
      base_url: baseUrl.trim() || undefined,
    }
  }

  function validateLocally(): string | null {
    if (!model.trim()) return 'Model name is required.'
    if (provider.requiresApiKey && apiKey.trim().length < 10) {
      return 'API key looks too short.'
    }
    if (providerId === 'openai_compatible' && !baseUrl.trim()) {
      return 'Base URL is required for custom providers.'
    }
    return null
  }

  async function runValidation() {
    const local = validateLocally()
    if (local) {
      setFormError(local)
      return
    }
    setFormError(null)
    setValidating(true)
    setStep('validate')
    try {
      const res = await api.validateProvider(payload())
      setResult(res)
    } catch (err) {
      setResult({
        ok: false,
        provider: providerId,
        model: model.trim(),
        base_url: baseUrl.trim(),
        api_key_set: !!apiKey.trim(),
        message: err instanceof ApiError ? err.message : (err as Error).message,
      })
    } finally {
      setValidating(false)
    }
  }

  async function saveAndFinish() {
    setSaving(true)
    setFormError(null)
    try {
      await api.saveProviderConfig(payload())
      setStep('done')
      // Small beat so the checkmark is visible, then hand off.
      setTimeout(onComplete, 400)
    } catch (err) {
      setFormError(
        err instanceof ApiError
          ? err.message
          : (err as Error).message || 'Failed to save settings.',
      )
      setStep('validate')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full w-full items-center justify-center overflow-y-auto bg-background p-8">
      <div className="w-full max-w-2xl">
        <div className="flex items-center gap-3">
          <img src={logo} alt="ALOS" className="h-10 w-10" />
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Welcome to ALOS
            </h1>
            <p className="text-xs text-muted-foreground">
              Let's connect your language model provider.
            </p>
          </div>
        </div>

        <StepIndicator step={step} />

        <div className="mt-6 rounded-xl border border-border bg-card p-6 shadow-lg">
          {step === 'provider' && (
            <ProviderPicker selected={providerId} onSelect={selectProvider} />
          )}

          {(step === 'credentials' || step === 'validate' || step === 'done') && (
            <CredentialsForm
              providerId={providerId}
              apiKey={apiKey}
              setApiKey={setApiKey}
              model={model}
              setModel={setModel}
              baseUrl={baseUrl}
              setBaseUrl={setBaseUrl}
              onBack={() => {
                setResult(null)
                setFormError(null)
                setStep('provider')
              }}
              onSubmit={runValidation}
              disabled={validating || saving || step === 'done'}
              formError={formError}
            />
          )}

          {(step === 'validate' || step === 'done') && (
            <ValidationResultPanel
              validating={validating}
              result={result}
              onRetry={runValidation}
              onSave={saveAndFinish}
              saving={saving}
              done={step === 'done'}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────

function StepIndicator({ step }: { step: Step }) {
  const steps: { id: Step; label: string }[] = [
    { id: 'provider', label: 'Choose provider' },
    { id: 'credentials', label: 'Enter credentials' },
    { id: 'validate', label: 'Validate & save' },
  ]
  const activeIdx = steps.findIndex(
    (s) => s.id === (step === 'done' ? 'validate' : step),
  )
  return (
    <div className="mt-6 flex items-center gap-2 text-xs text-muted-foreground">
      {steps.map((s, i) => (
        <div key={s.id} className="flex items-center gap-2">
          <span
            className={cn(
              'flex h-5 w-5 items-center justify-center rounded-full border text-[10px]',
              i <= activeIdx
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border',
            )}
          >
            {i + 1}
          </span>
          <span className={cn(i === activeIdx && 'text-foreground')}>
            {s.label}
          </span>
          {i < steps.length - 1 && (
            <ChevronRight className="h-3 w-3 opacity-50" />
          )}
        </div>
      ))}
    </div>
  )
}

function ProviderPicker({
  selected,
  onSelect,
}: {
  selected: ProviderId
  onSelect: (id: ProviderId) => void
}) {
  return (
    <div>
      <h2 className="text-sm font-semibold">Choose your provider</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        You can change this later in Settings.
      </p>
      <div className="mt-4 grid gap-2">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p.id)}
            className={cn(
              'group flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-left transition',
              'hover:border-primary hover:bg-primary/5',
              selected === p.id
                ? 'border-primary bg-primary/10'
                : 'border-border bg-background',
            )}
          >
            <div>
              <div className="text-sm font-medium">{p.label}</div>
              <div className="text-xs text-muted-foreground">{p.tagline}</div>
            </div>
            <ChevronRight className="mt-1 h-4 w-4 opacity-50 transition group-hover:opacity-100" />
          </button>
        ))}
      </div>
    </div>
  )
}

function CredentialsForm(props: {
  providerId: ProviderId
  apiKey: string
  setApiKey: (v: string) => void
  model: string
  setModel: (v: string) => void
  baseUrl: string
  setBaseUrl: (v: string) => void
  onBack: () => void
  onSubmit: () => void
  disabled: boolean
  formError: string | null
}) {
  const def = providerById(props.providerId)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        props.onSubmit()
      }}
    >
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">{def.label}</h2>
          <p className="text-xs text-muted-foreground">{def.tagline}</p>
        </div>
        <button
          type="button"
          onClick={props.onBack}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Change provider
        </button>
      </div>

      <div className="mt-5 grid gap-4">
        {def.requiresApiKey && (
          <Field label="API key" htmlFor="api_key">
            <input
              id="api_key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={props.apiKey}
              onChange={(e) => props.setApiKey(e.target.value)}
              placeholder="Paste your key here"
              className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40"
            />
            {def.keyHelpUrl && (
              <p className="mt-1 text-[11px] text-muted-foreground">
                Need one?{' '}
                <a
                  href={def.keyHelpUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline"
                >
                  {def.keyHelpUrl}
                </a>
              </p>
            )}
          </Field>
        )}

        <Field label="Model" htmlFor="model">
          <input
            id="model"
            list={`models-${def.id}`}
            value={props.model}
            onChange={(e) => props.setModel(e.target.value)}
            placeholder="Model identifier"
            className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40"
          />
          {def.modelSuggestions.length > 0 && (
            <datalist id={`models-${def.id}`}>
              {def.modelSuggestions.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          )}
        </Field>

        {def.baseUrlOverridable && (
          <Field label="Base URL" htmlFor="base_url">
            <input
              id="base_url"
              value={props.baseUrl}
              onChange={(e) => props.setBaseUrl(e.target.value)}
              placeholder={def.defaultBaseUrl || 'https://api.example.com/v1'}
              className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/40"
            />
            {def.defaultBaseUrl && (
              <p className="mt-1 text-[11px] text-muted-foreground">
                Defaults to{' '}
                <code className="rounded bg-muted px-1 py-0.5 font-mono">
                  {def.defaultBaseUrl}
                </code>
              </p>
            )}
          </Field>
        )}
      </div>

      {props.formError && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {props.formError}
        </div>
      )}

      <button
        type="submit"
        disabled={props.disabled}
        className="mt-5 w-full rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Test connection
      </button>
    </form>
  )
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="text-xs font-medium text-foreground">
        {label}
      </label>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}

function ValidationResultPanel({
  validating,
  result,
  onRetry,
  onSave,
  saving,
  done,
}: {
  validating: boolean
  result: ProviderValidationResult | null
  onRetry: () => void
  onSave: () => void
  saving: boolean
  done: boolean
}) {
  if (validating) {
    return (
      <div className="mt-5 flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Reaching out to provider…
      </div>
    )
  }
  if (!result) return null

  if (done) {
    return (
      <div className="mt-5 flex items-center gap-2 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-primary">
        <CheckCircle2 className="h-3.5 w-3.5" />
        Provider saved. Launching ALOS…
      </div>
    )
  }

  const ok = result.ok
  return (
    <div
      className={cn(
        'mt-5 rounded-md border px-3 py-3 text-xs',
        ok
          ? 'border-primary/30 bg-primary/10 text-primary'
          : 'border-destructive/40 bg-destructive/10 text-destructive',
      )}
    >
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 className="h-3.5 w-3.5" />
        ) : (
          <XCircle className="h-3.5 w-3.5" />
        )}
        <span className="font-semibold">
          {ok ? 'Provider reached successfully.' : 'Provider check failed.'}
        </span>
      </div>
      {result.message && (
        <p className="mt-1 text-[11px] opacity-90">{result.message}</p>
      )}
      {result.errors && result.errors.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-[11px] opacity-90">
          {result.errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex gap-2">
        {ok ? (
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="rounded-md bg-primary px-3 py-1.5 text-[11px] font-semibold text-primary-foreground disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save & continue'}
          </button>
        ) : (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-[11px] font-semibold text-foreground"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  )
}
