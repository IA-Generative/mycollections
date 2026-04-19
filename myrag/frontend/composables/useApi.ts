/**
 * MyRAG API composable — centralized API calls.
 *
 * Injects the user's current OIDC access_token as "Authorization: Bearer"
 * so that routes doing impersonation (e.g. /api/sources/drive/*) can relay
 * it to downstream services. The token is looked up lazily from useAuth
 * at call time so it stays in sync with silent renew.
 */
export function useApi() {
  const config = useRuntimeConfig()
  const baseUrl = config.public.myragApiUrl

  function authHeaders(): Record<string, string> {
    const { getAccessToken } = useAuth()
    const token = getAccessToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  async function get<T = any>(path: string, params?: Record<string, string>): Promise<T> {
    // baseUrl can be "" in prod (same-origin) — `new URL("/foo")` alone
    // throws "Invalid URL" without an explicit base, so we use the page
    // origin as the base for resolution.
    const base = baseUrl || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
    const url = new URL(`${baseUrl}${path}`, base)
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
    }
    const resp = await fetch(url.toString(), { headers: authHeaders() })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function post<T = any>(path: string, body?: any): Promise<T> {
    const resp = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function patch<T = any>(path: string, body?: any): Promise<T> {
    const resp = await fetch(`${baseUrl}${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function del<T = any>(path: string): Promise<T> {
    const resp = await fetch(`${baseUrl}${path}`, { method: 'DELETE', headers: authHeaders() })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function uploadFile(path: string, file: File, fields?: Record<string, string>) {
    const form = new FormData()
    form.append('file', file)
    if (fields) {
      Object.entries(fields).forEach(([k, v]) => form.append(k, v))
    }
    const resp = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: authHeaders(),          // Content-Type is set automatically for FormData
      body: form,
    })
    if (!resp.ok) throw new Error(`Upload error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  return { get, post, patch, del, uploadFile, baseUrl }
}
