import { AlosClient } from './client'
import { useAuth } from '@/store/auth'

/**
 * Global API client instance. Reads the API key from the auth store at
 * request time, so changes to the key take effect immediately without
 * needing to rebuild the client.
 */
export const api = new AlosClient({
  getApiKey: () => useAuth.getState().apiKey,
})

export { AlosClient, ApiError } from './client'
