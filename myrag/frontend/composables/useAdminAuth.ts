/**
 * Droit d'accès à l'administration (menu + routes /admin).
 *
 * L'interface ne déduit plus ce droit des groupes du jeton : la liste des groupes
 * administrateurs vit côté serveur (MYRAG_SUPERADMIN_GROUPES), qui répond à `/api/moi`.
 * Ce n'est qu'un affichage : la sécurité reste appliquée par l'API (app/services/access.py).
 */
export function useAdminAuth() {
  const etat = useState<boolean | null>('moi-superadmin', () => null)
  const { user } = useAuth()
  const config = useRuntimeConfig()

  /** Interroge le serveur une fois par session ; rend le droit. */
  async function charger(): Promise<boolean> {
    if (etat.value !== null) return etat.value
    if (config.public.authEnabled && !user.value) return false
    try {
      const moi = await useApi().get<{ superadmin: boolean }>('/api/moi')
      etat.value = !!moi?.superadmin
    } catch {
      etat.value = false
    }
    return etat.value
  }

  if (import.meta.client && etat.value === null && (user.value || !config.public.authEnabled)) charger()

  const isAdmin = computed(() => etat.value === true)
  return { isAdmin, charger }
}
