/**
 * Interroger une collection avec un agent de Mes agents — la part PURE du contrat d'agents
 * MirAI (docs/agents.md) : les portées OIDC à demander, la lecture des fiches, la lecture des
 * passages rendus par la recherche, la construction du message envoyé à l'agent, le sens des
 * erreurs. Rien ici ne touche au réseau ni à Vue : tout se teste tel quel.
 *
 * Le contenu des fiches est une donnée NON FIABLE (contrat) : texte brut, tailles bornées,
 * affiché par interpolation, jamais comme du HTML.
 */

/** La portée optionnelle qui ajoute l'audience `mesagents` (et les groupes en chemins) au jeton. */
export const PORTEE_OIDC_AGENTS = 'mesagents-agents'

/**
 * Les portées OIDC à demander au SSO : celles de base, plus `mesagents-agents` quand Mes agents
 * est branché. Un Keycloak REFUSE une portée qui n'est pas affectée au client (`invalid_scope`,
 * dès la connexion) : on ne la demande que si l'adresse de Mes agents est renseignée.
 */
export function portesOidc(base: string, mesagentsBaseUrl: string | null | undefined): string {
  const portees = base.split(/\s+/).filter(Boolean)
  if (String(mesagentsBaseUrl || '').trim() && !portees.includes(PORTEE_OIDC_AGENTS)) portees.push(PORTEE_OIDC_AGENTS)
  return portees.join(' ')
}

// ─── Les fiches ──────────────────────────────────────────────────────────────────────────────

/** Le vocabulaire fermé du contrat ; une valeur inconnue est ignorée, jamais affichée. */
export const ENTREES_CONNUES = ['text', 'selection', 'document', 'email', 'thread', 'meeting', 'collection', 'page'] as const
export type Entree = typeof ENTREES_CONNUES[number]

export interface FicheAgent {
  id: string
  name: string
  description: string
  origin: 'mine' | 'shared'
  status: 'draft' | 'published' | 'submitted'
  inputs: Entree[]
  /** Ce qui se passe dans `model` de `POST /v1/chat/completions` — égal à `id` aujourd'hui, sans qu'on le suppose. */
  model: string
  /** La page de l'agent dans Mes agents (https absolue), ou '' si la fiche n'en donne pas de valable. */
  url: string
}

const NOM_MAX = 200
const DESCRIPTION_MAX = 2000

function texte(v: unknown, max: number): string {
  if (typeof v !== 'string') return ''
  // Caractères de contrôle écartés (hors retours à la ligne, resserrés ensuite), taille bornée.
  const propre = v.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '').replace(/\s+/g, ' ').trim()
  return propre.length > max ? propre.slice(0, max - 1) + '…' : propre
}

function lireFiche(brut: unknown): FicheAgent | null {
  if (!brut || typeof brut !== 'object') return null
  const f = brut as Record<string, unknown>
  const id = texte(f.id, 200)
  const name = texte(f.name, NOM_MAX)
  const model = texte(f.model, 200) || id
  if (!id || !name || !model) return null
  const inputs = (Array.isArray(f.inputs) ? f.inputs : [])
    .filter((e): e is Entree => typeof e === 'string' && (ENTREES_CONNUES as readonly string[]).includes(e))
  const status = f.status === 'draft' || f.status === 'submitted' ? f.status : 'published'
  const url = typeof f.url === 'string' && /^https:\/\/[^\s"'<>]+$/.test(f.url) ? f.url : ''
  return {
    id, name, model, inputs, status, url,
    description: texte(f.description, DESCRIPTION_MAX),
    origin: f.origin === 'mine' ? 'mine' : 'shared',
  }
}

/** Un agent sait-il travailler sur une collection ? */
export function accepteCollection(fiche: Pick<FicheAgent, 'inputs'>): boolean {
  return fiche.inputs.includes('collection')
}

/**
 * Les fiches de `GET /api/v1/agents`, lues avec méfiance (formes vérifiées, textes bornés) et
 * filtrées sur `inputs ∋ collection` — le service filtre déjà sur `?input=collection`, on ne
 * s'y fie pas. L'ordre du service est gardé (les siens d'abord, puis les partagés).
 */
export function lireFiches(payload: unknown): FicheAgent[] {
  const brut = payload && typeof payload === 'object' ? (payload as Record<string, unknown>).agents : null
  if (!Array.isArray(brut)) return []
  const vues = new Set<string>()
  const fiches: FicheAgent[] = []
  for (const b of brut) {
    const f = lireFiche(b)
    if (!f || !accepteCollection(f) || vues.has(f.id)) continue
    vues.add(f.id)
    fiches.push(f)
  }
  return fiches
}

export function libelleOrigine(origin: FicheAgent['origin']): string {
  return origin === 'mine' ? 'Le vôtre' : 'Partagé par des collègues'
}

// ─── Les passages de la recherche ────────────────────────────────────────────────────────────

export interface Passage {
  /** Le numéro cité par l'agent : `[n]`, à partir de 1. */
  n: number
  titre: string
  snippet: string
  /** Le lien signé rendu par la recherche (absolu), ou null. */
  url: string | null
  page: number | null
}

/** Passages transmis au plus : huit documents, trois passages par document au plus côté serveur. */
export const PASSAGES_MAX = 16
const SNIPPET_MAX = 1000

/**
 * Les passages de `GET /api/v1/search` (contrat de recherche MirAI), à plat et numérotés dans
 * l'ordre du service : un document, puis ses passages. Un résultat sans texte est passé.
 */
export function passagesDepuisRecherche(payload: unknown, max = PASSAGES_MAX): Passage[] {
  const results = payload && typeof payload === 'object' ? (payload as Record<string, unknown>).results : null
  if (!Array.isArray(results)) return []
  const passages: Passage[] = []
  for (const r of results) {
    if (!r || typeof r !== 'object') continue
    const doc = r as Record<string, any>
    const titre = texte(doc.title, NOM_MAX) || 'Document'
    const urlDoc = typeof doc.url === 'string' && doc.url ? doc.url : null
    for (const h of Array.isArray(doc.hits) ? doc.hits : []) {
      if (passages.length >= max) return passages
      if (!h || typeof h !== 'object') continue
      const snippet = texte(h.snippet, SNIPPET_MAX)
      if (!snippet) continue
      const page = h.location && typeof h.location === 'object' ? h.location.page : null
      passages.push({
        n: passages.length + 1,
        titre,
        snippet,
        url: typeof h.url === 'string' && h.url ? h.url : urlDoc,
        page: Number.isInteger(page) && page > 0 ? page : null,
      })
    }
  }
  return passages
}

// ─── Le message envoyé à l'agent ─────────────────────────────────────────────────────────────

/** Un message `user` ne dépasse pas 20 000 caractères (contrat). */
export const MESSAGE_MAX = 20000
/** La question est aussi ce que cherche la recherche : `q` y est borné à 1 000 caractères. */
export const QUESTION_MAX = 1000

export const CONSIGNE = 'Réponds à partir des passages suivants, en citant [n].'

/**
 * Un texte tel qu'il peut entrer dans le bloc `<<< … >>>` : sur une ligne, sans suite de trois
 * chevrons (une ligne `<<<` ou `>>>` dans un passage ouvrirait ou fermerait le bloc). Deux
 * chevrons au plus, jamais trois : la neutralisation ne peut pas en recréer.
 */
export function neutraliser(texte: string): string {
  return String(texte ?? '').replace(/\s+/g, ' ').replace(/<{3,}/g, '<<').replace(/>{3,}/g, '>>').trim()
}

function ligne(p: Passage): string {
  return `[${p.n}] ${neutraliser(p.titre)} — ${neutraliser(p.snippet)}`
}

/**
 * Le dernier message `user` : la question, une consigne courte, puis les passages entre `<<<`
 * et `>>>` — la convention de contexte du contrat. Si tout ne tient pas dans `max`, les derniers
 * passages sont écartés : la réponse ne cite que ce qui a été transmis, d'où `passages` en retour.
 */
export function construireMessage(question: string, passages: Passage[], max = MESSAGE_MAX): { contenu: string, passages: Passage[] } {
  const tete = `${neutraliser(question).slice(0, QUESTION_MAX)}\n\n${CONSIGNE}\n\n<<<\n`
  const pied = '\n>>>'
  const gardes: Passage[] = []
  const lignes: string[] = []
  let taille = tete.length + pied.length
  for (const p of passages) {
    const l = ligne(p)
    const ajout = l.length + (lignes.length ? 1 : 0)
    if (taille + ajout > max) break
    taille += ajout
    lignes.push(l)
    gardes.push(p)
  }
  return { contenu: tete + lignes.join('\n') + pied, passages: gardes }
}

/** `choices[0].message.content` d'une réponse au format OpenAI ; '' si la forme n'y est pas. */
export function lireReponse(payload: unknown): string {
  const choices = payload && typeof payload === 'object' ? (payload as Record<string, any>).choices : null
  const contenu = Array.isArray(choices) ? choices[0]?.message?.content : null
  return typeof contenu === 'string' ? contenu : ''
}

/** Les numéros `[n]` cités dans la réponse, parmi les `nombre` passages transmis. */
export function citationsDansLaReponse(reponse: string, nombre: number): Set<number> {
  const citees = new Set<number>()
  for (const m of String(reponse ?? '').matchAll(/\[(\d{1,3})\]/g)) {
    const n = Number(m[1])
    if (n >= 1 && n <= nombre) citees.add(n)
  }
  return citees
}

// ─── Les sources sous la réponse ─────────────────────────────────────────────────────────────

/** Ce qu'attend `PlaygroundSourceChip` (les champs qu'il lit). */
export interface SourcePuce {
  n: number
  libelle: string
  titre_document: string
  chunk_url: string
  page?: number
  content: string
}

/**
 * Le lien signé de la recherche est absolu (`https://…/api/openrag/extract/<id>?exp=…&sig=…`).
 * La puce, elle, veut le chemin : `proxiedSourceUrl` garde intact un chemin `/api/openrag/…`
 * signé, mais réécrirait une adresse absolue en perdant la signature. On rend donc le chemin
 * et ses paramètres ; une adresse d'une autre forme reste telle quelle.
 */
export function cheminSigne(url: string | null | undefined): string {
  if (!url) return ''
  if (url.startsWith('/api/openrag/')) return url
  try {
    const u = new URL(url)
    if (u.pathname.startsWith('/api/openrag/')) return u.pathname + u.search
    return url
  } catch {
    return ''
  }
}

export function sourcesPourPuces(passages: Passage[]): SourcePuce[] {
  return passages.map(p => ({
    n: p.n,
    libelle: `[${p.n}] ${p.titre}`,
    titre_document: p.titre,
    chunk_url: cheminSigne(p.url),
    page: p.page ?? undefined,
    content: p.snippet,
  }))
}

/** Ce que « Copier » met dans le presse-papiers : la réponse, puis les passages transmis. */
export function texteACopier(reponse: string, passages: Passage[]): string {
  const corps = String(reponse ?? '').trim()
  if (!passages.length) return corps
  const lignes = passages.map(p => `[${p.n}] ${p.titre}${p.page ? ` (p. ${p.page})` : ''}${p.url ? ` — ${p.url}` : ''}`)
  return `${corps}\n\nPassages transmis à l'agent :\n${lignes.join('\n')}`
}

// ─── Les erreurs ─────────────────────────────────────────────────────────────────────────────

export interface ErreurAgents {
  /** `masquer` : la fonction disparaît sans bloquer l'écran ; `message` : à dire à la personne. */
  genre: 'masquer' | 'message'
  message: string
  code: string
}

function codeEtMessage(corps: unknown): { code: string, message: string } {
  const e = corps && typeof corps === 'object' ? (corps as Record<string, any>).error : null
  if (!e || typeof e !== 'object') return { code: '', message: '' }
  return { code: typeof e.code === 'string' ? e.code : '', message: texte(e.message, DESCRIPTION_MAX) }
}

/**
 * Le sens d'une réponse de Mes agents (liste ou lancement), d'après le contrat :
 * - `injoignable`, 401 `invalid_token`, 403 (`audience_mismatch`, `forbidden`) → la fonction se masque ;
 * - 422 `blocked_input` / `blocked_output` → `message` s'affiche tel quel ;
 * - 404 → l'agent n'est plus accessible ; 429 → réessayer ; 502 → l'agent ne répond pas ;
 * - `delai` : pas de réponse dans le délai accordé (120 s au lancement).
 */
export function normaliserErreurAgents(statut: number | 'injoignable' | 'delai', corps?: unknown): ErreurAgents {
  if (statut === 'injoignable') return { genre: 'masquer', code: 'unreachable', message: 'Mes agents est injoignable.' }
  if (statut === 'delai') return { genre: 'message', code: 'timeout', message: "L'agent n'a pas répondu dans le délai accordé (deux minutes). Réessayez dans un moment." }
  const { code, message } = codeEtMessage(corps)
  if (statut === 401 || statut === 403) {
    return { genre: 'masquer', code: code || (statut === 401 ? 'invalid_token' : 'forbidden'), message: 'Votre session ne permet pas de lancer un agent.' }
  }
  if (statut === 422) {
    return { genre: 'message', code: code || 'blocked', message: message || "L'agent a refusé cette demande." }
  }
  if (statut === 404) return { genre: 'message', code: code || 'model_not_found', message: "Cet agent n'est plus accessible." }
  if (statut === 429) return { genre: 'message', code: code || 'rate_limited', message: 'Trop de demandes : réessayez dans un moment.' }
  if (statut === 502) return { genre: 'message', code: code || 'llm_unavailable', message: "L'agent ne répond pas. Réessayez dans un moment." }
  if (statut === 400) return { genre: 'message', code: code || 'invalid_query', message: message || 'Mes agents a refusé la demande.' }
  return { genre: 'message', code: code || `http_${statut}`, message: `Mes agents a répondu par une erreur (${statut}). Réessayez dans un instant.` }
}

/** Le sens d'une erreur de `GET /api/v1/search` (notre recherche), avant même de lancer l'agent. */
export function messageErreurRecherche(statut: number | 'injoignable' | 'delai', corps?: unknown): string {
  if (statut === 'injoignable') return 'Mes collections ne répond pas. Vérifiez votre connexion, puis réessayez.'
  if (statut === 'delai') return "La recherche dans la collection n'a pas abouti dans le délai accordé. Réessayez dans un moment."
  const { message } = codeEtMessage(corps)
  switch (statut) {
    case 400: return message || 'La recherche a refusé cette question.'
    case 401:
    case 403: return "Votre session ne permet pas de chercher dans cette collection. Reconnectez-vous, puis réessayez."
    case 429: return 'Trop de recherches : réessayez dans un instant.'
    case 503: return 'Recherche momentanément indisponible : réessayez dans un instant.'
    default: return `La recherche a répondu par une erreur (${statut}). Réessayez dans un instant.`
  }
}
