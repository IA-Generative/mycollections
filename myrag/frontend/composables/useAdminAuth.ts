/**
 * Droit d'accès à l'administration (menu + routes /admin).
 *
 * Admin = membre du groupe Keycloak /myrag/superadmin, lu depuis les groupes du
 * jeton (mêmes groupes que ceux exploités côté backend). N'est qu'un affichage :
 * la sécurité reste appliquée par l'API (app/services/access.py).
 */
export function useAdminAuth() {
  const { getUserGroups } = useAuth()
  const isAdmin = computed(() => isAdminGroup(getUserGroups()))
  return { isAdmin }
}
