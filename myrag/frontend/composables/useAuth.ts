/**
 * Keycloak OIDC authentication composable.
 * Uses oidc-client-ts with PKCE flow.
 */

export function useAuth() {
  const config = useRuntimeConfig()
  const user = useState<any>('auth-user', () => null)
  const loading = useState('auth-loading', () => true)
  const authError = useState('auth-error', () => '')

  async function init() {
    // Skip auth if disabled or server-side
    if (!config.public.authEnabled || import.meta.server) {
      loading.value = false
      return
    }

    loading.value = true
    authError.value = ''

    try {
      const { UserManager, WebStorageStateStore } = await import('oidc-client-ts')

      const keycloakUrl = config.public.keycloakUrl || 'http://host.docker.internal:8082'
      const keycloakRealm = config.public.keycloakRealm || 'openwebui'
      const clientId = config.public.keycloakClientId || 'myrag-front'
      // Strip non-standard ports from origin (e.g. :3000 injected by reverse proxy)
      const rawOrigin = window.location.origin
      const origin = rawOrigin.replace(/:(80|443|3000|8201)$/, '')
      // IMPORTANT: keep this in sync with the path test below. We send
      // /auth/callback (no trailing slash) so Keycloak returns the user to
      // the exact same path — trailing-slash mismatches between the declared
      // redirect_uri and window.location.pathname caused a fast redirect
      // loop in prod (/auth/callback/ vs /auth/callback).
      const redirectUri = `${origin}/auth/callback`

      const mgr = new UserManager({
        authority: `${keycloakUrl}/realms/${keycloakRealm}`,
        client_id: clientId,
        redirect_uri: redirectUri,
        post_logout_redirect_uri: origin,
        response_type: 'code',
        scope: 'openid email profile',
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
        automaticSilentRenew: true,
      })

      // Case 1: returning from Keycloak callback (accept with or without
      // trailing slash — some proxies/servers normalize one way or the other).
      const normalizedPath = window.location.pathname.replace(/\/+$/, '')
      if (normalizedPath === '/auth/callback') {
        try {
          const signed = await mgr.signinRedirectCallback()
          user.value = {
            access_token: signed.access_token,
            profile: signed.profile,
          }
          loading.value = false
          // Full navigation to "/" — window.history.replaceState alone would
          // change the URL bar but Nuxt router would keep rendering the
          // callback page forever (stuck on "Connexion en cours...").
          window.location.replace('/')
          return
        } catch (cbError: any) {
          // Do NOT auto-retry signinRedirect here — if the callback itself is
          // broken (stale state, clock skew, missing redirect_uri), an auto
          // retry creates an infinite loop. Surface the error to the user.
          console.error('OIDC callback error:', cbError)
          authError.value = `Callback error: ${cbError.message || cbError}`
          await mgr.removeUser()
          window.sessionStorage.clear()
          loading.value = false
          return
        }
      }

      // Case 2: check existing session
      try {
        const existingUser = await mgr.getUser()
        if (existingUser && !existingUser.expired) {
          user.value = {
            access_token: existingUser.access_token,
            profile: existingUser.profile,
          }
          loading.value = false
          return
        }
      } catch (e) {
        // Session invalid, clear and redirect
        await mgr.removeUser()
      }

      // Case 3: no session — redirect to Keycloak
      await mgr.signinRedirect()

    } catch (e: any) {
      console.error('Auth init error:', e)
      authError.value = e.message || 'Authentication error'
      loading.value = false
    }
  }

  /**
   * Force a silent renew via oidc-client-ts (uses the refresh_token stored
   * in sessionStorage). Used by useApi as a recovery step when a fetch
   * returns 401 — `automaticSilentRenew` is best-effort and can fail
   * silently (3rd-party cookies, Safari ITP, iframe blocked, etc.).
   *
   * Returns the new access_token on success, null on failure.
   */
  async function renewToken(): Promise<string | null> {
    if (!config.public.authEnabled || import.meta.server) return null
    try {
      const { UserManager, WebStorageStateStore } = await import('oidc-client-ts')
      const keycloakUrl = config.public.keycloakUrl
      const keycloakRealm = config.public.keycloakRealm
      const clientId = config.public.keycloakClientId
      const rawOrigin = window.location.origin
      const origin = rawOrigin.replace(/:(80|443|3000|8201)$/, '')
      const redirectUri = `${origin}/auth/callback`

      const mgr = new UserManager({
        authority: `${keycloakUrl}/realms/${keycloakRealm}`,
        client_id: clientId,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: 'openid email profile',
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      })
      const renewed = await mgr.signinSilent()
      if (!renewed) return null
      user.value = {
        access_token: renewed.access_token,
        profile: renewed.profile,
      }
      return renewed.access_token
    } catch (e) {
      console.warn('silent renew failed:', e)
      return null
    }
  }

  async function logout() {
    try {
      const { UserManager, WebStorageStateStore } = await import('oidc-client-ts')
      const keycloakUrl = config.public.keycloakUrl
      const keycloakRealm = config.public.keycloakRealm
      const mgr = new UserManager({
        authority: `${keycloakUrl}/realms/${keycloakRealm}`,
        client_id: config.public.keycloakClientId,
        redirect_uri: window.location.origin,
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      })
      await mgr.signoutRedirect()
    } catch (e) {
      window.sessionStorage.clear()
      window.location.href = '/'
    }
  }

  function getAccessToken(): string | null {
    return user.value?.access_token || null
  }

  function getUserName(): string {
    const p = user.value?.profile
    if (!p) return ''
    return p.preferred_username || p.name || p.email || ''
  }

  function getUserGroups(): string[] {
    return user.value?.profile?.groups || []
  }

  return { user, loading, authError, init, logout, renewToken, getAccessToken, getUserName, getUserGroups }
}
