/**
 * Keycloak OIDC authentication composable.
 * Uses oidc-client-ts with PKCE flow.
 */

// `basic` est un scope Keycloak qui ajoute `sub` (et `auth_time`) au jeton d'ACCÈS.
// Sans lui, ce realm n'y met pas `sub` : les services qui identifient leur utilisateur
// par ce claim — Drive, par exemple — refusent l'appel avec un 401 dont rien ne dit
// qu'il s'agit d'un claim manquant.
//
// Il doit être DEMANDÉ tant qu'il est assigné au client en scope « optionnel ». S'il
// passe un jour en « par défaut », cette demande devient sans effet, pas nuisible.
const OIDC_SCOPES = 'openid email profile basic'

// UN SEUL UserManager pour toute la vie de la page, et c'est un correctif : trois
// fabrications séparées (init, renew, logout) faisaient que `automaticSilentRenew`
// renouvelait le jeton dans le sessionStorage SANS que l'état Vue ne l'apprenne —
// l'application continuait d'envoyer l'ancien jeton jusqu'à expiration (les 401 à
// 6 minutes mesurés en charge le 2026-08-24). Le singleton porte l'écouteur
// `addUserLoaded`, seul endroit d'où l'état Vue est resynchronisé.
let _mgr: any = null
// Dédoublonnage des renouvellements : deux appels API simultanés en 401 déclenchaient
// deux `signinSilent()` concurrents sur le même refresh token.
let _renouvellement: Promise<string | null> | null = null

export function useAuth() {
  const config = useRuntimeConfig()
  const user = useState<any>('auth-user', () => null)
  const loading = useState('auth-loading', () => true)
  const authError = useState('auth-error', () => '')

  // La bulle du menu commun de la bêta est alimentée par l'application : événement
  // `mirai-menu:identite` (le menu peut être construit avant OU après la session), et
  // `window.MIRAI_MENU.sub` pour le condensé des avis — jamais écrit en clair.
  function poserUtilisateur(u: any) {
    user.value = { access_token: u.access_token, profile: u.profile }
    try {
      const p = u.profile || {}
      ;(window as any).MIRAI_MENU = Object.assign((window as any).MIRAI_MENU || {}, {
        sub: p.sub || '',
      })
      document.dispatchEvent(new CustomEvent('mirai-menu:identite', {
        detail: { nom: p.name || p.preferred_username || '', mail: p.email || '' },
      }))
    } catch { /* le menu affichera « ? » */ }
  }

  async function manager() {
    if (_mgr) return _mgr
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

    _mgr = new UserManager({
      authority: `${keycloakUrl}/realms/${keycloakRealm}`,
      client_id: clientId,
      redirect_uri: redirectUri,
      post_logout_redirect_uri: origin,
      response_type: 'code',
      scope: OIDC_SCOPES,
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      automaticSilentRenew: true,
    })
    // C'est CET écouteur qui rend `automaticSilentRenew` utile : sans lui, la
    // bibliothèque renouvelle en silence et l'application n'en sait rien.
    _mgr.events.addUserLoaded((u: any) => { poserUtilisateur(u) })
    return _mgr
  }

  async function init() {
    // Skip auth if disabled or server-side
    if (!config.public.authEnabled || import.meta.server) {
      loading.value = false
      return
    }

    loading.value = true
    authError.value = ''

    try {
      const mgr = await manager()

      // Case 1: returning from Keycloak callback (accept with or without
      // trailing slash — some proxies/servers normalize one way or the other).
      const normalizedPath = window.location.pathname.replace(/\/+$/, '')
      if (normalizedPath === '/auth/callback') {
        try {
          const signed = await mgr.signinRedirectCallback()
          poserUtilisateur(signed)
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
          poserUtilisateur(existingUser)
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
    if (_renouvellement) return _renouvellement
    _renouvellement = (async () => {
      try {
        const mgr = await manager()
        const renewed = await mgr.signinSilent()
        if (!renewed) return null
        // `addUserLoaded` a déjà resynchronisé l'état Vue.
        return renewed.access_token
      } catch (e) {
        console.warn('silent renew failed:', e)
        return null
      } finally {
        _renouvellement = null
      }
    })()
    return _renouvellement
  }

  async function logout() {
    try {
      const mgr = await manager()
      // `post_logout_redirect_uri` est dans la configuration du singleton : le SSO ferme
      // la session (id_token_hint) puis REVIENT sur l'application — avant ce réglage,
      // l'utilisateur restait sur la page « Vous êtes déconnecté » de Keycloak.
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
