/**
 * Les assistants de recherche côté écran (lot B) : libellés, état, formulaire de création,
 * fiche envoyée au serveur (B1), consignes (B2), trace du plan suivi. Fonctions pures, testées dans
 * tests/unit/assistants.test.ts. Le contrat fait foi : `myrag/app/harnais/contrat.py`
 * (FicheAssistant, Consigne, Plan, Resultat) ; le serveur reste seul juge des droits.
 */

export type Regime = 'toujours' | 'selon_question' | 'sur_consigne'
export type TypeSource = 'collection' | 'connecteur'
export type Canal = 'socle' | 'portail' | 'fenetre_js' | 'api'

export interface SourceFiche { id: string, type: TypeSource, regime: Regime, rang?: number | null }
export interface Canaux { socle: boolean, portail: boolean, fenetre_js: boolean, api: boolean }

/** Une étape d'une consigne : une source de l'assistant, et ce qu'elle reçoit de l'étape d'avant. */
export interface EtapeConsigne { source: string, avec?: string | null }
/** Une consigne : quand (une phrase, des exemples) / chercher (des sources, dans l'ordre) / répondre. */
export interface Consigne {
  id: string
  quand: string
  exemples: string[]
  chercher: EtapeConsigne[]
  repondre: string
  gabarit?: string | null
}

export interface FicheAssistant {
  contrat: 1
  assistant: string
  titre: string
  rubrique: string | null
  description: string
  sources: SourceFiche[]
  consignes: Consigne[]
  seuil_fiable: number
  validation_requise: boolean
  publication: Canaux
}

/** Même motif que IDENT_ASSISTANT du contrat. */
export const IDENT_ASSISTANT = /^[a-z0-9][a-z0-9._-]{2,63}$/

/** Les régimes, dits sans jargon : quand l'assistant interroge cette source. */
export const REGIMES: readonly { cle: Regime, libelle: string, aide: string }[] = [
  { cle: 'selon_question', libelle: 'Si la question s\'y rapporte', aide: 'L\'assistant l\'interroge quand la question ressemble à ce que la source contient.' },
  { cle: 'toujours', libelle: 'Toujours', aide: 'Interrogée pour chaque question.' },
  { cle: 'sur_consigne', libelle: 'Seulement si une consigne la cite', aide: 'Réservée aux cas que vous décrivez dans les consignes.' },
]

export function libelleRegime (r: Regime): string {
  return REGIMES.find(x => x.cle === r)?.libelle || r
}

/** Où l'assistant peut être servi, dit simplement. */
export const CANAUX: readonly { cle: Canal, libelle: string, aide: string }[] = [
  { cle: 'socle', libelle: 'Mon assistant', aide: 'Il apparaît dans la liste des modèles de Mon assistant.' },
  { cle: 'portail', libelle: 'Mon portail', aide: 'Ses réponses s\'affichent dans la recherche de Mon portail.' },
  { cle: 'fenetre_js', libelle: 'Une fenêtre sur un site', aide: 'Une ligne à coller dans une page intranet ouvre l\'assistant dans une fenêtre.' },
  { cle: 'api', libelle: 'L\'API', aide: 'D\'autres applications l\'interrogent, sur clé d\'API.' },
]

export const CANAUX_VIDES: Canaux = { socle: false, portail: false, fenetre_js: false, api: false }

export function canauxActifs (c: Partial<Canaux> | null | undefined): string[] {
  return CANAUX.filter(x => c?.[x.cle]).map(x => x.libelle)
}

/** « Brouillon » tant qu'aucune version n'est publiée, sinon « Version n ». */
export function etatAssistant (version: number | null | undefined): { libelle: string, classe: string } {
  return version ? { libelle: `Version ${version}`, classe: 'fr-badge--success' } : { libelle: 'Brouillon', classe: 'fr-badge--info' }
}

/** « 3 sources » ; et, si le serveur en a masqué (illisibles pour vous), « dont 1 que vous ne voyez pas ». */
export function resumeSources (visibles: number, masquees: number): string {
  const total = visibles + masquees
  const base = `${total} source${total > 1 ? 's' : ''}`
  return masquees ? `${base}, dont ${masquees} que vous ne pouvez pas lire` : base
}

export interface FormulaireAssistant {
  titre: string
  identifiant: string
  description: string
  rubrique: string
  sources: { id: string, regime: Regime }[]
}

/** Les erreurs du formulaire de création, par champ ; vide = prêt à envoyer. */
export function validerFormulaire (f: FormulaireAssistant): Record<string, string> {
  const e: Record<string, string> = {}
  if (!f.titre.trim()) {
    e.titre = 'Donnez un titre à l\'assistant.'
  }
  if (!IDENT_ASSISTANT.test(f.identifiant)) {
    e.identifiant = 'Minuscules, chiffres, tirets ou points, 3 à 64 caractères, en commençant par une lettre ou un chiffre.'
  }
  if (!f.sources.length) {
    e.sources = 'Choisissez au moins une collection.'
  }
  else if (f.sources.length > 20) {
    e.sources = 'Vingt sources au plus.'
  }
  if (f.description.length > 2000) {
    e.description = '2000 caractères au plus.'
  }
  return e
}

/** La fiche envoyée par `PUT /api/assistants/{id}` : le contrat, rien de plus. */
export function ficheDepuisFormulaire (f: FormulaireAssistant, publication: Canaux = CANAUX_VIDES): FicheAssistant {
  return {
    contrat: 1,
    assistant: f.identifiant,
    titre: f.titre.trim(),
    rubrique: f.rubrique || null,
    description: f.description.trim(),
    sources: f.sources.map((s, i) => ({ id: s.id, type: 'collection', regime: s.regime, rang: i + 1 })),
    consignes: [],
    seuil_fiable: 0.9,
    validation_requise: false,
    publication: { ...publication },
  }
}

const ECHAPPE_ATTRIBUT: Record<string, string> = { '&': '&amp;', '"': '&quot;', '<': '&lt;', '>': '&gt;' }
const A_ECHAPPER = /[&"<>]/g
const BARRES_FINALES = /\/+$/

/** La ligne à coller dans une page pour ouvrir l'assistant dans une fenêtre (canal `fenetre_js`). */
export function ligneFenetre (id: string, base: string): string {
  const b = base.replace(BARRES_FINALES, '').replace(A_ECHAPPER, c => ECHAPPE_ATTRIBUT[c]!)
  const i = id.replace(A_ECHAPPER, c => ECHAPPE_ATTRIBUT[c]!)
  return `<script src="${b}/fenetre.js" data-assistant="${i}" defer></script>`
}

// ─── Les consignes (B2) ──────────────────────────────────────────────────────────────────────

/** Valeur réservée de `quand` : la consigne vaut pour toute question (QUAND_TOUJOURS du contrat). */
export const QUAND_TOUJOURS = 'toujours'
/** Même motif que IDENT_RELAIS du contrat : le nom de ce qu'une étape reçoit de la précédente. */
export const IDENT_RELAIS = /^[a-z][a-z0-9_]{1,40}$/
/** Les bornes de `Consigne` et de `FicheAssistant.consignes` dans le contrat. */
export const BORNES_CONSIGNE = { quand: 500, exemples: 10, exemple: 500, repondre: 4000, consignes: 50 } as const

/** Une consigne neuve, d'identifiant libre parmi celles de la fiche (`consigne-1`, `consigne-2`…). */
export function consigneVide (existantes: readonly Pick<Consigne, 'id'>[] = []): Consigne {
  const pris = new Set(existantes.map(c => c.id))
  let n = existantes.length + 1
  while (pris.has(`consigne-${n}`)) {
    n++
  }
  return { id: `consigne-${n}`, quand: '', exemples: [], chercher: [], repondre: '' }
}

/** « Pour toute question », ou la phrase de la consigne. */
export function libelleQuand (quand: string | null | undefined): string {
  const q = (quand || '').trim()
  return q === QUAND_TOUJOURS ? 'Pour toute question' : q
}

/**
 * Les erreurs d'une consigne, par champ ; vide = conforme au contrat. `sources` : les sources de
 * l'assistant ; `autres` : les autres consignes de la fiche (une seule peut valoir « toujours »).
 */
export function validerConsigne (c: Consigne, sources: readonly string[], autres: readonly Consigne[] = []): Record<string, string> {
  const e: Record<string, string> = {}
  const quand = c.quand.trim()
  if (!IDENT_ASSISTANT.test(c.id) || autres.some(a => a.id === c.id)) {
    e.id = 'Identifiant de consigne invalide ou déjà pris.'
  }
  if (!quand) {
    e.quand = 'Dites quand la consigne s\'applique.'
  }
  else if (quand.length > BORNES_CONSIGNE.quand) {
    e.quand = `${BORNES_CONSIGNE.quand} caractères au plus.`
  }
  else if (quand === QUAND_TOUJOURS && autres.some(a => a.quand.trim() === QUAND_TOUJOURS)) {
    e.quand = 'Une seule consigne peut valoir pour toute question.'
  }
  const exemples = c.exemples.map(x => x.trim())
  if (exemples.length > BORNES_CONSIGNE.exemples) {
    e.exemples = `${BORNES_CONSIGNE.exemples} exemples au plus.`
  }
  else if (exemples.some(x => !x || x.length > BORNES_CONSIGNE.exemple)) {
    e.exemples = `Un exemple fait entre 1 et ${BORNES_CONSIGNE.exemple} caractères.`
  }
  const etapes: string[] = []
  c.chercher.forEach((etape, i) => {
    if (!sources.includes(etape.source)) {
      etapes.push(`Étape ${i + 1} : choisissez une source de l'assistant.`)
    }
    const avec = etape.avec?.trim()
    if (avec && i === 0) {
      etapes.push('La première étape ne reçoit rien : rien n\'a encore été trouvé.')
    }
    else if (avec && !IDENT_RELAIS.test(avec)) {
      etapes.push(`Étape ${i + 1} : ce qui est transmis se nomme en minuscules, sans espace ni accent (ex. article_trouve).`)
    }
  })
  if (etapes.length) {
    e.chercher = etapes.join(' ')
  }
  if (c.repondre.trim().length > BORNES_CONSIGNE.repondre) {
    e.repondre = `${BORNES_CONSIGNE.repondre} caractères au plus.`
  }
  return e
}

/**
 * Déplace l'étape `de` à la place `vers` (liste neuve ; hors bornes, rien ne bouge). Dans tous les
 * cas, la première étape perd son « avec » : le contrat le refuse, rien n'a encore été trouvé.
 */
export function ordonnerEtapes (etapes: readonly EtapeConsigne[], de: number, vers: number): EtapeConsigne[] {
  const liste = etapes.map(e => ({ ...e }))
  if (de >= 0 && de < liste.length && vers >= 0 && vers < liste.length && de !== vers) {
    const [deplacee] = liste.splice(de, 1)
    liste.splice(vers, 0, deplacee!)
  }
  if (liste[0]?.avec) {
    liste[0] = { ...liste[0], avec: null }
  }
  return liste
}

/** Déplace un élément d'un cran (liste neuve) ; sans effet aux bords. */
export function deplacer<T> (liste: readonly T[], i: number, sens: -1 | 1): T[] {
  const copie = [...liste]
  const j = i + sens
  if (i < 0 || i >= copie.length || j < 0 || j >= copie.length) {
    return copie
  }
  ;[copie[i], copie[j]] = [copie[j]!, copie[i]!]
  return copie
}

/** Les exemples saisis un par ligne : lignes vides retirées, espaces rognés. */
export function exemplesDepuisTexte (texte: string): string[] {
  return texte.split('\n').map(l => l.trim()).filter(Boolean)
}

/** La consigne telle que le contrat l'attend : textes rognés, « avec » vide retiré. */
export function consignePourEnvoi (c: Consigne): Consigne {
  const sortie: Consigne = {
    id: c.id,
    quand: c.quand.trim(),
    exemples: c.exemples.map(x => x.trim()).filter(Boolean),
    chercher: c.chercher.map((e, i) => {
      const avec = e.avec?.trim()
      return avec && i > 0 ? { source: e.source, avec } : { source: e.source }
    }),
    repondre: c.repondre.trim(),
  }
  if (c.gabarit) {
    sortie.gabarit = c.gabarit
  }
  return sortie
}

/** Ce que dit une consigne en une ligne : « 3 exemples · Collection A → Collection B ». */
export function resumeConsigne (c: Consigne, titre: (id: string) => string = id => id): string {
  const morceaux: string[] = []
  if (c.exemples.length) {
    morceaux.push(`${c.exemples.length} exemple${c.exemples.length > 1 ? 's' : ''}`)
  }
  morceaux.push(c.chercher.length ? c.chercher.map(e => titre(e.source)).join(' → ') : 'Sources choisies par l\'assistant')
  return morceaux.join(' · ')
}

// ─── Le plan suivi et son résultat (« Tester » des consignes, bac à sable) ───────────────────

export interface EtapePlan { n: number, source: string, question: string, poids?: number, attend?: number[], avec?: string | null }
export interface PlanAssistant {
  assistant: string
  version: number
  planificateur: 'toutes_les_sources' | 'regles' | 'llm'
  consigne?: string | null
  score_consigne?: number | null
  reponse_fiable?: { id: string, score: number } | null
  etapes: EtapePlan[]
  sources_ignorees?: number
  a_valider?: boolean
}
export interface PassageAssistant {
  source: string
  etape: number
  rang: number
  score?: number | null
  ident?: string | null
  document: string
  titre?: string
  date?: string | null
  page?: number | null
  texte: string
  url?: string | null
  meta?: Record<string, unknown>
}
export interface ResultatAssistant {
  plan: PlanAssistant
  passages: PassageAssistant[]
  reponse?: string | null
  duree_ms: number
  par_source?: Record<string, number>
}

const METHODES: Record<string, string> = {
  toutes_les_sources: 'Toutes les sources, sans tri',
  regles: 'Selon les consignes',
  llm: 'Au jugé, d\'après la question',
}

export interface TraceEtape { n: number, source: string, titre: string, apres: number[], avec: string | null, passages: number }
export interface TracePlan {
  /** Comment l'assistant a choisi où chercher, dit simplement. */
  methode: string
  /** La consigne retenue (son « quand ») et la confiance, en pourcentage, s'il y en a une. */
  consigne: { id: string, libelle: string, score: number | null } | null
  reponseFiable: boolean
  etapes: TraceEtape[]
  /** Les sources de l'assistant que ce plan n'a pas interrogées (titres). */
  nonInterrogees: string[]
  /** Les sources écartées parce que la personne ne peut pas les lire : un compte, jamais des noms. */
  ecartees: number
  duree: string | null
}

/**
 * La trace d'un plan, prête à afficher : la consigne retenue, les étapes (source, ce dont chacune
 * part, combien de passages), les sources non interrogées et le compte des sources écartées.
 */
export function traceDuPlan (
  plan: PlanAssistant,
  fiche: Pick<FicheAssistant, 'sources' | 'consignes'> | null,
  titre: (id: string) => string = id => id,
  resultat?: Pick<ResultatAssistant, 'passages' | 'duree_ms'> | null,
): TracePlan {
  const consigne = plan.consigne ? fiche?.consignes.find(c => c.id === plan.consigne) : null
  const parEtape = new Map<number, number>()
  for (const p of resultat?.passages || []) {
    parEtape.set(p.etape, (parEtape.get(p.etape) || 0) + 1)
  }
  const interrogees = new Set(plan.etapes.map(e => e.source))
  return {
    methode: METHODES[plan.planificateur] || plan.planificateur,
    consigne: plan.consigne
      ? {
          id: plan.consigne,
          libelle: consigne ? libelleQuand(consigne.quand) : plan.consigne,
          score: typeof plan.score_consigne === 'number' ? Math.round(plan.score_consigne * 100) : null,
        }
      : null,
    reponseFiable: !!plan.reponse_fiable,
    etapes: [...plan.etapes].sort((a, b) => a.n - b.n).map(e => ({
      n: e.n,
      source: e.source,
      titre: titre(e.source),
      apres: e.attend || [],
      avec: e.avec || null,
      passages: parEtape.get(e.n) || 0,
    })),
    nonInterrogees: (fiche?.sources || []).filter(s => !interrogees.has(s.id)).map(s => titre(s.id)),
    ecartees: plan.sources_ignorees || 0,
    duree: typeof resultat?.duree_ms === 'number' ? `${(resultat.duree_ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s` : null,
  }
}

/** Un passage sous la forme d'une puce de source (`PlaygroundSourceChip`) : titre, page, texte, lien. */
export function sourceDuPassage (p: PassageAssistant, titreSource: (id: string) => string = id => id): Record<string, string | number | undefined> {
  const titre = p.titre || p.document
  return {
    // La clé de dédoublonnage des puces : un document d'une source.
    original_filename: `${p.source}/${p.document}`,
    libelle: titre,
    titre_document: `${titre} — ${titreSource(p.source)}`,
    page: p.page ?? undefined,
    content: p.texte,
    chunk_url: p.url || undefined,
  }
}
