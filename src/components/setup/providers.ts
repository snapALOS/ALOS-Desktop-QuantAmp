import type { ProviderId } from '@/types/api'

export interface ProviderDef {
  id: ProviderId
  label: string
  tagline: string
  defaultModel: string
  defaultBaseUrl: string
  /** Whether the provider accepts a user-supplied base_url override. */
  baseUrlOverridable: boolean
  /** Whether an API key is required from the user. */
  requiresApiKey: boolean
  /** Example models shown as hints in the model input. */
  modelSuggestions: string[]
  /** Where the user would get their key, for the help link. */
  keyHelpUrl?: string
}

export const PROVIDERS: ProviderDef[] = [
  {
    id: 'nvidia',
    label: 'NVIDIA NIM',
    tagline: 'Hosted Nemotron and partner models via NVIDIA.',
    defaultModel: 'nvidia/nemotron-3-super-120b-a12b',
    defaultBaseUrl: 'https://integrate.api.nvidia.com/v1',
    baseUrlOverridable: true,
    requiresApiKey: true,
    modelSuggestions: [
      'nvidia/nemotron-3-super-120b-a12b',
      'meta/llama-3.1-70b-instruct',
      'mistralai/mixtral-8x22b-instruct-v0.1',
    ],
    keyHelpUrl: 'https://build.nvidia.com/',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    tagline: 'GPT-4o, o-series, and other OpenAI models.',
    defaultModel: 'gpt-4o-mini',
    defaultBaseUrl: '',
    baseUrlOverridable: false,
    requiresApiKey: true,
    modelSuggestions: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'gpt-4.1'],
    keyHelpUrl: 'https://platform.openai.com/api-keys',
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    tagline: 'Claude Sonnet, Opus, and Haiku.',
    defaultModel: 'claude-sonnet-4-5',
    defaultBaseUrl: '',
    baseUrlOverridable: false,
    requiresApiKey: true,
    modelSuggestions: [
      'claude-sonnet-4-5',
      'claude-opus-4-5',
      'claude-haiku-4-5',
    ],
    keyHelpUrl: 'https://console.anthropic.com/settings/keys',
  },
  {
    id: 'ollama',
    label: 'Ollama (local)',
    tagline: 'Run models locally — no API key needed.',
    defaultModel: 'llama3.1',
    defaultBaseUrl: 'http://localhost:11434/v1',
    baseUrlOverridable: true,
    requiresApiKey: false,
    modelSuggestions: ['llama3.1', 'qwen2.5:14b', 'deepseek-r1:14b'],
    keyHelpUrl: 'https://ollama.com/',
  },
  {
    id: 'openai_compatible',
    label: 'Custom (OpenAI-compatible)',
    tagline: 'Any OpenAI-spec endpoint — Together, Groq, vLLM, etc.',
    defaultModel: '',
    defaultBaseUrl: '',
    baseUrlOverridable: true,
    requiresApiKey: true,
    modelSuggestions: [],
  },
]

export function providerById(id: ProviderId): ProviderDef {
  return PROVIDERS.find((p) => p.id === id) ?? PROVIDERS[0]
}
