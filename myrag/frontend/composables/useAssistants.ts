import type { FicheAssistant } from '~/utils/assistants'

/** Les appels de la fiche d'un assistant (`/api/assistants`, lot 0) : le serveur juge des droits. */
export function useAssistants () {
  const { get, put, post } = useApi()
  const ident = (id: string) => encodeURIComponent(id)
  return {
    lister: async () => (await get('/api/assistants')).assistants || [],
    lire: (id: string) => get(`/api/assistants/${ident(id)}`),
    enregistrer: (fiche: FicheAssistant) => put(`/api/assistants/${ident(fiche.assistant)}`, fiche),
    publier: (id: string) => post(`/api/assistants/${ident(id)}/publier`),
    versions: async (id: string) => (await get(`/api/assistants/${ident(id)}/versions`)).versions || [],
  }
}
