import { invoke } from '@/api/tauri'

/**
 * Creates a scoped invoke function for a specific module.
 * 
 * Enforces the ALOS naming convention: `<module_id>_<verb>`
 * 
 * @example
 * const forge = createModuleInvoke('forge')
 * forge('open_file', { path: '/foo.txt' }) // calls invoke('forge_open_file', ...)
 */
export function createModuleInvoke(moduleId: string) {
  return async function invokeModule<T>(
    verb: string,
    args?: Record<string, unknown>,
  ): Promise<T> {
    const fullName = `${moduleId}_${verb}`
    return invoke<T>(fullName, args)
  }
}
