import type { Collection } from '~/types/collection'
import { titreDe } from '~/utils/catalogue'

/**
 * Le titre lisible des sources d'un assistant : celui de la collection quand la personne la voit,
 * l'identifiant sinon. Une seule lecture de `/api/collections` par page.
 */
export function useTitresSources () {
  const { get } = useApi()
  const collections = ref<Collection[]>([])
  onMounted(async () => {
    try {
      collections.value = (await get('/api/collections')).collections || []
    }
    catch {}
  })
  function titre (id: string): string {
    const c = collections.value.find(x => x.name === id)
    return c ? titreDe(c) : id
  }
  return { collections, titre }
}
