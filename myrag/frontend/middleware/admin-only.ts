/**
 * Protège les routes /admin : seuls les super-admins (/myrag/superadmin) passent.
 *
 * Défense en profondeur — la sécurité réelle est appliquée par l'API. Application
 * SPA (ssr:false) : on n'évalue que côté client. Tant que l'utilisateur n'est pas
 * encore chargé (init OIDC asynchrone), on ne bloque pas (le menu reste masqué et
 * l'API refuse les données) ; on ne redirige que si un non-admin est confirmé.
 */
export default defineNuxtRouteMiddleware(() => {
  if (import.meta.server) return
  const config = useRuntimeConfig()
  if (!config.public.authEnabled) return

  const { user } = useAuth()
  if (!user.value) return // auth pas encore prête : ne pas bloquer

  if (!isAdminGroup(user.value.profile?.groups)) {
    return navigateTo('/')
  }
})
