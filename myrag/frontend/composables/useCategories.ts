/**
 * Les rubriques du catalogue. Tout le monde les lit ; les régler (créer, renommer,
 * ordonner, classer les collections) est réservé à l'administration — l'API refuse
 * sinon, l'écran ne fait que masquer.
 */
import type { Categorie } from '~/types/collection'

export function useCategories() {
  const { get, post, patch, put, del } = useApi()

  return {
    lister: async (): Promise<Categorie[]> => (await get('/api/categories')).categories || [],
    creer: (corps: { cle: string; libelle: string; description?: string }) => post('/api/categories', corps),
    modifier: (cle: string, corps: { libelle?: string; description?: string }) => patch(`/api/categories/${cle}`, corps),
    supprimer: (cle: string) => del(`/api/categories/${cle}`),
    ordonner: (cles: string[]) => put('/api/categories/ordre', { cles }),
    affecter: (affectations: Record<string, string | null>) => put('/api/categories/affectations', { affectations }),
  }
}
