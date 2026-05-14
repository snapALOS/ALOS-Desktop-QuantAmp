import type { AlosClient } from '@/api/client'

export interface ModuleAgentContext extends Record<string, unknown> {
  module_id: string
  module_name: string
  captured_at: string
  payload: Record<string, unknown>
}

export type ModuleAgentContextProvider = () => ModuleAgentContext | Promise<ModuleAgentContext>

const providers = new Map<string, ModuleAgentContextProvider>()

export function registerModuleAgentContextProvider(
  moduleId: string,
  provider: ModuleAgentContextProvider,
) {
  providers.set(moduleId, provider)
  return () => {
    if (providers.get(moduleId) === provider) providers.delete(moduleId)
  }
}

export async function getModuleAgentContext(
  moduleId: string,
  moduleName: string,
  api: AlosClient,
): Promise<ModuleAgentContext> {
  const provider = providers.get(moduleId)
  if (provider) {
    try {
      return boundContext(await provider(), moduleId, moduleName)
    } catch (error) {
      return fallbackContext(moduleId, moduleName, {
        provider_error: error instanceof Error ? error.message : String(error),
      })
    }
  }

  if (moduleId === 'atlas') {
    try {
      const repos = await api.atlasListRepos()
      const firstRepo = repos.repositories?.[0]
      const status = firstRepo ? await api.atlasStatus(firstRepo.repo_id || firstRepo.path).catch(() => null) : null
      return fallbackContext(moduleId, moduleName, { repositories: repos.repositories?.slice(0, 20) || [], status })
    } catch (error) {
      return fallbackContext(moduleId, moduleName, { error: error instanceof Error ? error.message : String(error) })
    }
  }

  if (moduleId === 'chamber') {
    try {
      const [summary, chambers] = await Promise.all([
        api.chamberGateSummary().catch(() => null),
        api.chamberList().catch(() => null),
      ])
      return fallbackContext(moduleId, moduleName, {
        gates: summary?.gates?.slice(0, 20) || [],
        counts: summary?.counts || {},
        chambers: chambers?.chambers?.slice(0, 20) || [],
      })
    } catch (error) {
      return fallbackContext(moduleId, moduleName, { error: error instanceof Error ? error.message : String(error) })
    }
  }

  if (moduleId === 'settings') {
    try {
      const settings = await api.getSettings()
      return fallbackContext(moduleId, moduleName, {
        configured: settings.configured,
        provider: settings.llm_provider,
        model: settings.model_name,
        api_key_set: settings.api_key_set,
        safety: {
          chamber_gate_required: settings.chamber_gate_required,
          allow_chamber_override: settings.allow_chamber_override,
          autonomous_write_mode: settings.autonomous_write_mode,
        },
      })
    } catch (error) {
      return fallbackContext(moduleId, moduleName, { error: error instanceof Error ? error.message : String(error) })
    }
  }

  return fallbackContext(moduleId, moduleName, {
    note: 'No module-specific context provider registered yet.',
  })
}

function boundContext(context: ModuleAgentContext, moduleId: string, moduleName: string): ModuleAgentContext {
  return fallbackContext(
    context.module_id || moduleId,
    context.module_name || moduleName,
    context.payload || {},
    context.captured_at,
  )
}

function fallbackContext(
  moduleId: string,
  moduleName: string,
  payload: Record<string, unknown>,
  capturedAt = new Date().toISOString(),
): ModuleAgentContext {
  return {
    module_id: moduleId,
    module_name: moduleName,
    captured_at: capturedAt,
    payload,
  }
}
