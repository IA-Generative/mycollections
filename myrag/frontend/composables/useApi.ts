/**
 * MyRAG API composable — centralized API calls.
 *
 * Responsibilities
 * - Resolve same-origin URLs even when baseUrl is empty.
 * - Inject the current OIDC access_token as `Authorization: Bearer` (looked up
 *   lazily via useAuth so silent renew is transparent).
 * - On a 401, try ONE silent renew via useAuth.renewToken(), then retry the
 *   request. If the second attempt still 401s, propagate — the layout or
 *   caller will surface the error or kick the user back to a fresh login.
 *
 * The one-shot retry is intentional: if refreshing doesn't fix the 401 (e.g.
 * the backend itself rejects, not token-related), we don't loop.
 */
export function useApi() {
  const config = useRuntimeConfig()
  const baseUrl = config.public.myragApiUrl

  function authHeaders(): Record<string, string> {
    const { getAccessToken } = useAuth()
    const token = getAccessToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  async function tryRenew(): Promise<boolean> {
    const { renewToken } = useAuth()
    const t = await renewToken()
    return !!t
  }

  async function fetchWithAuth(url: string, init: RequestInit = {}): Promise<Response> {
    const doFetch = () =>
      fetch(url, {
        ...init,
        headers: {
          ...(init.headers || {}),
          ...authHeaders(),
        },
      })

    let resp = await doFetch()
    if (resp.status === 401) {
      const renewed = await tryRenew()
      if (renewed) {
        resp = await doFetch()   // retry once with the new token
      }
    }
    return resp
  }

  async function get<T = any>(path: string, params?: Record<string, string>): Promise<T> {
    // baseUrl can be "" in prod (same-origin) — `new URL("/foo")` alone
    // throws "Invalid URL" without an explicit base.
    const base = baseUrl || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
    const url = new URL(`${baseUrl}${path}`, base)
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
    }
    const resp = await fetchWithAuth(url.toString(), { method: 'GET' })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function post<T = any>(path: string, body?: any): Promise<T> {
    const resp = await fetchWithAuth(`${baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function patch<T = any>(path: string, body?: any): Promise<T> {
    const resp = await fetchWithAuth(`${baseUrl}${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function del<T = any>(path: string): Promise<T> {
    const resp = await fetchWithAuth(`${baseUrl}${path}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function uploadFile(path: string, file: File, fields?: Record<string, string>) {
    const form = new FormData()
    form.append('file', file)
    if (fields) {
      Object.entries(fields).forEach(([k, v]) => form.append(k, v))
    }
    // Note: Content-Type is set automatically by fetch for FormData.
    const resp = await fetchWithAuth(`${baseUrl}${path}`, {
      method: 'POST',
      body: form,
    })
    if (!resp.ok) throw new Error(`Upload error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  return { get, post, patch, del, uploadFile, baseUrl }
}
