/** Les appels du réseau d'entraide. Rien de calculé ici : les états viennent du serveur. */
export function useEntraide () {
  const { get, post } = useApi()

  return {
    listerAppels: (params?: Record<string, string>) => get('/api/entraide', params),
    lireAppel: (id: string) => get(`/api/entraide/appels/${encodeURIComponent(id)}`),
    creerAppel: (corps: { type: string, titre: string, texte: string }) => post('/api/entraide/appels', corps),
    recommandations: (id: string) => get(`/api/entraide/appels/${id}/recommandations`),
    publierAppel: (id: string) => post(`/api/entraide/appels/${id}/publier`),
    cloreAppel: (id: string) => post(`/api/entraide/appels/${id}/clore`),
    repondre: (id: string, texte: string) => post(`/api/entraide/appels/${id}/reponses`, { texte }),
  }
}
