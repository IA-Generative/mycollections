import type { Capacites } from '~/utils/capacites'
/**
 * Les capacités : d'abord ce que le SERVEUR applique (`/api/config` — le menu commun, plus la
 * surcharge de l'environnement d'une prévisualisation), puis, s'il ne répond pas, le menu commun
 * en même origine (`/_beta/capacites.json`). Un seul chargement, partagé par toutes les pages :
 * aucun bouton n'apparaît avant de savoir, et aucun n'apparaît que le serveur refuserait.
 */
import { ref } from 'vue'
import { CAPACITES_DEFAUT, normaliserCapacites } from '~/utils/capacites'

const capacites = ref<Capacites>({ ...CAPACITES_DEFAUT })
const chargees = ref(false)
let enCours: Promise<void> | null = null

export function useCapacites () {
  async function charger () {
    if (chargees.value) {
      return
    }
    if (enCours) {
      return enCours
    }
    enCours = (async () => {
      try {
        const { get } = useApi()
        capacites.value = normaliserCapacites(await get('/api/config'))
        chargees.value = true
        return
      }
      catch {}
      try {
        const r = await fetch('/_beta/capacites.json', { signal: AbortSignal.timeout(4000) })
        if (r.ok) {
          capacites.value = normaliserCapacites(await r.json())
        }
      }
      catch {}
      chargees.value = true
    })()
    return enCours
  }
  return { capacites, chargees, charger }
}
