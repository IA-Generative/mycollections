/**
 * Mes agents — les agents que la personne peut lancer sur une collection, et le lancement
 * lui-même (contrat d'agents MirAI, docs/agents.md).
 *
 * Tout se passe dans le navigateur, avec le jeton de la session : Mes collections ne relaie
 * rien côté serveur. Lancer, c'est d'abord demander à NOTRE recherche (`/api/v1/search`, qui
 * applique les droits de la collection) les passages qui répondent, puis les confier à l'agent
 * (`POST /v1/chat/completions` de Mes agents) avec le même jeton.
 *
 * La liste est gardée trois minutes et partagée par toutes les pages. Un refus (jeton,
 * audience, groupe) ou un service injoignable MASQUE la fonction sans bloquer l'écran ; la
 * liste se redemande passé le délai de garde.
 */
import { computed, ref } from 'vue'
import {
  citationsDansLaReponse, construireMessage, lireFiches, lireReponse, messageErreurRecherche,
  normaliserErreurAgents, passagesDepuisRecherche, sourcesPourPuces,
  type FicheAgent, type Passage, type SourcePuce,
} from '~/utils/agents'

const CACHE_MS = 3 * 60 * 1000
const DELAI_LISTE_MS = 8000
const DELAI_RECHERCHE_MS = 15000
/** Le contrat demande au moins 120 s : la garde de sortie attend la réponse entière. */
const DELAI_LANCEMENT_MS = 120000
/** Documents demandés à la recherche (au plus trois passages par document côté serveur). */
const DOCUMENTS_MAX = 8

type Etat = 'inconnu' | 'ok' | 'masque'

const fiches = ref<FicheAgent[]>([])
const etat = ref<Etat>('inconnu')
let verifieA = 0
let enCours: Promise<void> | null = null

export interface ResultatAgent {
  agent: FicheAgent
  question: string
  /** La réponse de l'agent, en Markdown à assainir avant tout rendu. */
  reponse: string
  /** Les passages réellement transmis (ceux qui tenaient dans le message). */
  passages: Passage[]
  sources: SourcePuce[]
  /** Les numéros `[n]` que la réponse cite. */
  citees: Set<number>
}

export type Lancement =
  | { ok: true, resultat: ResultatAgent }
  | { ok: false, genre: 'masquer' | 'message' | 'vide', message: string }

function delaiOuReseau(e: unknown): 'delai' | 'injoignable' {
  return (e as any)?.name === 'TimeoutError' ? 'delai' : 'injoignable'
}

export function useMesAgents() {
  const config = useRuntimeConfig()
  const base = String(config.public.mesagentsBaseUrl || '').trim().replace(/\/+$/, '')
  /** Mes agents est branché (adresse renseignée au build) : sans elle, la fonction n'existe pas. */
  const configure = base !== ''

  /** Un appel à Mes agents avec le jeton de la session ; un 401 vaut un renouvellement puis un second essai. */
  async function appeler(chemin: string, init: RequestInit, delaiMs: number): Promise<Response> {
    const { getAccessToken, renewToken } = useAuth()
    const envoyer = (jeton: string | null) => fetch(`${base}${chemin}`, {
      ...init,
      headers: { ...(init.headers || {}), ...(jeton ? { Authorization: `Bearer ${jeton}` } : {}) },
      signal: AbortSignal.timeout(delaiMs),
    })
    let resp = await envoyer(getAccessToken())
    if (resp.status === 401) {
      const neuf = await renewToken()
      if (neuf) resp = await envoyer(neuf)
    }
    return resp
  }

  /** La liste, filtrée sur les agents qui acceptent une collection. Un seul appel par délai de garde. */
  async function lister(force = false): Promise<void> {
    if (!configure) { etat.value = 'masque'; return }
    if (!force && verifieA && Date.now() - verifieA < CACHE_MS) return
    if (enCours) return enCours
    enCours = (async () => {
      try {
        const resp = await appeler(`/api/v1/agents?input=collection&limit=200`, { method: 'GET' }, DELAI_LISTE_MS)
        if (resp.ok) {
          fiches.value = lireFiches(await resp.json())
          etat.value = 'ok'
        } else {
          const e = normaliserErreurAgents(resp.status, await resp.json().catch(() => null))
          // Un refus masque ; une autre erreur (429, 5xx) laisse l'état tel quel — réessai passé le délai.
          if (e.genre === 'masquer') { etat.value = 'masque'; fiches.value = [] }
        }
      } catch {
        etat.value = 'masque'
        fiches.value = []
      } finally {
        verifieA = Date.now()
        enCours = null
      }
    })()
    return enCours
  }

  /** Les passages de la collection qui répondent à la question — par notre recherche, avec ses droits. */
  async function chercher(question: string, collection: string): Promise<{ ok: true, passages: Passage[] } | { ok: false, message: string }> {
    const api = useApi()
    const origine = api.baseUrl || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost')
    const url = new URL(`${api.baseUrl}/api/v1/search`, origine)
    url.searchParams.set('q', question)
    url.searchParams.set('scope', collection)
    url.searchParams.set('limit', String(DOCUMENTS_MAX))
    let resp: Response
    try {
      resp = await api.fetchWithAuth(url.toString(), { method: 'GET', signal: AbortSignal.timeout(DELAI_RECHERCHE_MS) })
    } catch (e) {
      return { ok: false, message: messageErreurRecherche(delaiOuReseau(e)) }
    }
    if (!resp.ok) return { ok: false, message: messageErreurRecherche(resp.status, await resp.json().catch(() => null)) }
    return { ok: true, passages: passagesDepuisRecherche(await resp.json().catch(() => null)) }
  }

  /** Lance `agent` sur les passages de `collection` qui répondent à `question`. Ne lève jamais. */
  async function lancer(agent: FicheAgent, question: string, collection: string): Promise<Lancement> {
    const q = question.trim()
    if (!q) return { ok: false, genre: 'message', message: 'Posez une question.' }

    const recherche = await chercher(q, collection)
    if (!recherche.ok) return { ok: false, genre: 'message', message: recherche.message }
    if (!recherche.passages.length) {
      return { ok: false, genre: 'vide', message: "Aucun passage de la collection ne répond à cette question : l'agent n'a pas été lancé." }
    }

    const { contenu, passages } = construireMessage(q, recherche.passages)
    let resp: Response
    try {
      resp = await appeler('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: agent.model, messages: [{ role: 'user', content: contenu }], stream: false }),
      }, DELAI_LANCEMENT_MS)
    } catch (e) {
      const err = normaliserErreurAgents(delaiOuReseau(e))
      return { ok: false, genre: err.genre, message: err.message }
    }
    if (!resp.ok) {
      const err = normaliserErreurAgents(resp.status, await resp.json().catch(() => null))
      if (err.genre === 'masquer') { etat.value = 'masque'; fiches.value = [] }
      return { ok: false, genre: err.genre, message: err.message }
    }
    const reponse = lireReponse(await resp.json().catch(() => null))
    if (!reponse) return { ok: false, genre: 'message', message: "L'agent a répondu sans texte. Réessayez dans un moment." }
    return {
      ok: true,
      resultat: {
        agent, question: q, reponse, passages,
        sources: sourcesPourPuces(passages),
        citees: citationsDansLaReponse(reponse, passages.length),
      },
    }
  }

  return {
    configure,
    fiches,
    etat,
    /** La fonction s'affiche : branchée, et la liste obtenue sans refus. */
    disponible: computed(() => configure && etat.value === 'ok'),
    lister,
    lancer,
  }
}
