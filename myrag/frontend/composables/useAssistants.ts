import type { FicheAssistant, ReponseMoteur, ResultatAssistant } from '~/utils/assistants'
import { reponseDoublure } from '~/utils/assistants'

/**
 * Les appels de la fiche d'un assistant (`/api/assistants`, lot 0) et de son exécution
 * (`/api/v1/assistants/{id}/executer`, servie par la doublure sur les installations où le moteur n'est
 * pas branché : elle le dit dans un en-tête) :
 * le serveur juge des droits.
 */
export function useAssistants () {
  const { get, put, post, fetchWithAuth, baseUrl } = useApi()
  const ident = (id: string) => encodeURIComponent(id)
  return {
    lister: async () => (await get('/api/assistants')).assistants || [],
    lire: (id: string) => get(`/api/assistants/${ident(id)}`),
    enregistrer: (fiche: FicheAssistant) => put(`/api/assistants/${ident(fiche.assistant)}`, fiche),
    publier: (id: string) => post(`/api/assistants/${ident(id)}/publier`),
    versions: async (id: string) => (await get(`/api/assistants/${ident(id)}/versions`)).versions || [],
    /**
     * Pose une question à l'assistant (depuis « Tester » ou le bac à sable) : le plan suivi, les passages, la réponse
     *  s'il y en a une ; `doublure` dit que le moteur n'est pas branché et que la réponse est un exemple.
     */
    executer: async (id: string, question: string): Promise<ReponseMoteur> => {
      const resp = await fetchWithAuth(`${baseUrl}/api/v1/assistants/${ident(id)}/executer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, canal: 'bac-a-sable' }),
      })
      if (!resp.ok) {
        throw new Error(`API error ${resp.status}: ${await resp.text()}`)
      }
      return { resultat: await resp.json() as ResultatAssistant, doublure: reponseDoublure(resp.headers) }
    },
  }
}
