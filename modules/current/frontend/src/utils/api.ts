import { useAuth } from '@/store/auth';

const ALOS_API_BASE = import.meta.env.VITE_ALOS_API_BASE || 'http://localhost:8000';

function currentPath(path: string): string {
  if (path.startsWith('/api/')) return `/api/current/${path.slice('/api/'.length)}`;
  if (path.startsWith('/')) return `/api/current${path}`;
  return `/api/current/${path}`;
}

export function storedApiToken(): string {
  return useAuth.getState().apiKey || '';
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has('content-type') && options.body) {
    headers.set('content-type', 'application/json');
  }
  const token = storedApiToken();
  if (token) headers.set('authorization', `Bearer ${token}`);

  const response = await fetch(`${ALOS_API_BASE}${currentPath(path)}`, { ...options, headers });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok || payload.error || payload.detail) {
    throw new Error(payload.detail || payload.error || `AlosCurrent request failed: ${response.status}`);
  }
  return payload as T;
}

export function apiBase(): string {
  return ALOS_API_BASE;
}

export function eventStreamUrl(path: string, params: Record<string, string | undefined> = {}): string {
  const url = new URL(`${ALOS_API_BASE}${currentPath(path)}`);
  const token = storedApiToken();
  if (token) url.searchParams.set('api_key', token);
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value);
  }
  return url.toString();
}
