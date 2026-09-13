/**
 * Les capacités déclarées par le menu commun (`/_beta/capacites.json`, même origine),
 * repli sur `/api/config` (la valeur que le serveur applique). Un seul chargement,
 * partagé par toutes les pages : aucun bouton n'apparaît avant de savoir.
 */
import { ref } from 'vue'
import { CAPACITES_DEFAUT, normaliserCapacites, type Capacites } from '~/utils/capacites'

const capacites = ref<Capacites>({ ...CAPACITES_DEFAUT })
const chargees = ref(false)
let enCours: Promise<void> | null = null

export function useCapacites() {
  async function charger() {
    if (chargees.value) return
    if (enCours) return enCours
    enCours = (async () => {
      try {
        const r = await fetch('/_beta/capacites.json', { signal: AbortSignal.timeout(4000) })
        if (r.ok) {
          capacites.value = normaliserCapacites(await r.json())
          chargees.value = true
          return
        }
      } catch {}
      try {
        const { get } = useApi()
        capacites.value = normaliserCapacites(await get('/api/config'))
      } catch {}
      chargees.value = true
    })()
    return enCours
  }
  return { capacites, chargees, charger }
}
