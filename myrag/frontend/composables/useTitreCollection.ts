/**
 * Le titre d'une collection connue par son seul identifiant (les sous-pages de
 * /c/<id> ne chargent pas toutes la fiche). Rend tout de suite l'identifiant rendu
 * lisible, puis le vrai titre dès que la fiche répond ; un titre déjà lu n'est pas
 * redemandé d'une page à l'autre.
 */
import { titreDe, titreDepuisNom } from '~/utils/catalogue'

export function useTitreCollection(id: string, options: { charger?: boolean } = {}) {
  const connus = useState<Record<string, string>>('titres-collections', () => ({}))
  const titre = computed(() => connus.value[id] || titreDepuisNom(id))

  /** À appeler par une page qui a déjà la fiche en main : évite un second appel. */
  function retenir(collection: { name: string; titre?: string } | null | undefined) {
    if (collection?.name) connus.value = { ...connus.value, [collection.name]: titreDe(collection) }
  }

  onMounted(async () => {
    // `charger: false` : la page lit déjà la fiche, elle appellera retenir().
    if (options.charger === false || connus.value[id]) return
    try {
      retenir(await useApi().get(`/api/collections/${id}`))
    } catch (e) { /* partition sans fiche, ou fiche illisible : le repli suffit */ }
  })

  return { titre, retenir }
}
