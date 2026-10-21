import type { FicheAssistant, ReponseMoteur, ResultatAssistant } from '~/utils/assistants'
import { reponseDoublure } from '~/utils/assistants'

/**
 * Les appels de la fiche d'un assistant (`/api/assistants`, lot 0) et de son exécution
 * (`/api/v1/assistants/{id}/executer`, servie par la doublure sur les installations où le moteur n'est
 * pas branché : elle le dit dans un en-tête) :
 * le serveur juge des droits.
 */
export function useAssistants () {
  const { get, put, post, patch, fetchWithAuth, baseUrl } = useApi()
  const ident = (id: string) => encodeURIComponent(id)
  return {
    lister: async () => (await get('/api/assistants')).assistants || [],
    lire: (id: string) => get(`/api/assistants/${ident(id)}`),
    enregistrer: (fiche: FicheAssistant) => put(`/api/assistants/${ident(fiche.assistant)}`, fiche),
    publier: (id: string) => post(`/api/assistants/${ident(id)}/publier`),
    /** Retire l'assistant (rien n'est effacé) ; un assistant miroir suit sa collection et refuse (409). */
    archiver: (id: string) => post(`/api/assistants/${ident(id)}/archiver`),
    /** Le jeu de questions réuni des sources que la personne lit (lecture seule) ; filtres `relecture`, `fiable`, `q`. */
    questionsQualite: (id: string, params?: Record<string, string>) => get(`/api/assistants/${ident(id)}/qualite/questions`, params),
    /** Par source lisible : la synthèse de qualité, les réponses fiables et combien de fois elles ont été servies. */
    qualite: (id: string) => get(`/api/assistants/${ident(id)}/qualite`),
    /** Marquer ou retirer une réponse fiable : le `PATCH` de la collection, avec ses droits (le serveur refuse qui ne la gère pas). */
    marquerFiable: (collection: string, question: string, fiable: boolean) =>
      patch(`/api/collections/${encodeURIComponent(collection)}/qualite/questions/${encodeURIComponent(question)}`, { fiable }),
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
