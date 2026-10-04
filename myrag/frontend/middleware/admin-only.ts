/**
 * Protège les routes /admin : seuls les administrateurs (MYRAG_SUPERADMIN_GROUPES, dit par
 * `/api/moi`) passent. Défense en profondeur : la sécurité réelle est appliquée par l'API.
 * Tant que le compte n'est pas chargé (init OIDC asynchrone, faite par le gabarit), on laisse
 * passer : le gabarit refait le contrôle une fois le compte chargé.
 */
export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return
  const config = useRuntimeConfig()
  if (!config.public.authEnabled) return

  const { user } = useAuth()
  if (!user.value) return

  const { charger } = useAdminAuth()
  if (!(await charger())) return navigateTo('/')
})
