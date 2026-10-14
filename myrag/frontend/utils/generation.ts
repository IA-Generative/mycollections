/**
 * L'onglet « Questions générées » : ce qu'il affiche se calcule ici, en fonctions pures testées
 * (tests/unit/generation.test.ts). Les états viennent du serveur ; l'écran les dit en français.
 */

export interface Compteurs {
  appels_llm: number
  tokens_entree: number
  tokens_sortie: number
  reparations_json: number
  inachevees: number
  erreurs_llm: number
  refus_debit?: number
  appels_embeddings: number
}

export interface Run {
  id: string
  etat: 'en_attente' | 'en_cours' | 'termine' | 'erreur'
  phase: string
  actif: boolean
  taille: number
  personas: { id: string, nom: string }[]
  morceaux_envoyes: number
  fichiers_collection: number
  paires_obtenues: number
  paires_echouees: number
  compteurs: Compteurs
  duree_s: number | null
  erreur: string | null
  modele: string
  cree_le: string
}

export interface Contexte { chunk_id: string, file_id: string, fichier: string, page: string | null, texte: string }
export interface Paire {
  id: string
  question: string
  reponse: string
  persona: string
  style: string
  longueur: string
  relecture: 'brut' | 'valide' | 'rejete'
  commentaire: string
  contextes: Contexte[]
}

const ETATS: Record<string, string> = {
  en_attente: 'En attente', en_cours: 'En cours', termine: 'Terminée', erreur: 'En échec',
}
const PHASES: Record<string, string> = {
  attente: "En attente d'une place",
  lecture: 'Lecture des passages',
  extraction: 'Repérage des sujets de chaque passage',
  generation: 'Rédaction des questions et des réponses',
  enregistrement: 'Enregistrement',
  fini: 'Terminée',
}
const RELECTURES: Record<string, string> = { brut: 'À relire', valide: 'Validée', rejete: 'Rejetée' }
const STYLES: Record<string, string> = {
  PERFECT_GRAMMAR: 'bien rédigée', POOR_GRAMMAR: 'syntaxe approximative',
  MISSPELLED: 'avec des fautes', WEB_SEARCH_LIKE: 'mots-clés',
}
const LONGUEURS: Record<string, string> = { SHORT: 'courte', MEDIUM: 'moyenne', LONG: 'longue' }

export const libelleEtatRun = (e: string) => ETATS[e] || e
export const libellePhase = (p: string) => PHASES[p] || p
export const libelleRelecture = (r: string) => RELECTURES[r] || r
export const libelleStyle = (s: string) => STYLES[s] || s
export const libelleLongueur = (l: string) => LONGUEURS[l] || l
/** Modèle de rédaction ; vide = la requête part sans nom, le serveur en aval choisit (mode direct d'OpenRAG). */
export const libelleModele = (m: string) => (m || '').trim() ? m : 'celui du serveur'

export const classeEtatRun = (e: string) => ({
  termine: 'fr-badge--success', erreur: 'fr-badge--error', en_cours: 'fr-badge--info', en_attente: 'fr-badge--new',
}[e] || '')
export const classeRelecture = (r: string) => ({ valide: 'fr-badge--success', rejete: 'fr-badge--error' }[r] || '')

/** « 1 h 02 min », « 3 min 10 s », « 42 s ». */
export function dureeLisible(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s) || s < 0) return ''
  const t = Math.round(s)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const sec = t % 60
  if (h) return `${h} h ${String(m).padStart(2, '0')} min`
  if (m) return `${m} min ${String(sec).padStart(2, '0')} s`
  return `${sec} s`
}

/** 215 300 → « 215 k », 950 → « 950 ». */
export function nombreCourt(n: number): string {
  if (!Number.isFinite(n)) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} M`
  if (n >= 10_000) return `${Math.round(n / 1000)} k`
  return n.toLocaleString('fr-FR')
}

/** Le coût d'un run en une ligne : « 195 appels · 215 k jetons · 3 réparations · 4 min 50 s ». */
export function resumeCout(run: Pick<Run, 'compteurs' | 'duree_s'>): string {
  const c = run.compteurs
  const morceaux = [
    `${c.appels_llm} appel${c.appels_llm > 1 ? 's' : ''} au modèle`,
    `${nombreCourt(c.tokens_entree + c.tokens_sortie)} jetons (${nombreCourt(c.tokens_entree)} lus, ${nombreCourt(c.tokens_sortie)} écrits)`,
  ]
  if (c.reparations_json) morceaux.push(`${c.reparations_json} réponse${c.reparations_json > 1 ? 's' : ''} mal formée${c.reparations_json > 1 ? 's' : ''} réparée${c.reparations_json > 1 ? 's' : ''}`)
  if (c.erreurs_llm) morceaux.push(`${c.erreurs_llm} erreur${c.erreurs_llm > 1 ? 's' : ''} du modèle`
    + (c.refus_debit ? ` (dont ${c.refus_debit} refus de quota)` : ''))
  const d = dureeLisible(run.duree_s)
  if (d) morceaux.push(d)
  return morceaux.join(' · ')
}

/** Une progressionRun indicative (0-100) : la phase dit où l'on est, les appels où l'on en est. */
export function progressionRun(run: Pick<Run, 'etat' | 'phase' | 'morceaux_envoyes' | 'taille' | 'compteurs'>): number {
  if (run.etat === 'termine' || run.etat === 'erreur') return 100
  const appels = run.compteurs?.appels_llm || 0
  switch (run.phase) {
    case 'attente': return 0
    case 'lecture': return 5
    case 'extraction': {
      const n = Math.max(1, run.morceaux_envoyes)
      return 10 + Math.round(50 * Math.min(1, appels / n))
    }
    case 'generation': {
      const fait = Math.max(0, appels - run.morceaux_envoyes)
      return 60 + Math.round(35 * Math.min(1, fait / Math.max(1, 2 * run.taille)))
    }
    case 'enregistrement': return 97
    default: return 0
  }
}

export interface ErreursPersona { nom?: string, description_role?: string }
export function validerPersona(p: { nom: string, description_role: string }, existants: string[] = []): ErreursPersona {
  const e: ErreursPersona = {}
  const nom = (p.nom || '').trim()
  const desc = (p.description_role || '').trim()
  if (!nom) e.nom = 'Donnez un nom au persona.'
  else if (nom.length > 120) e.nom = '120 caractères au plus.'
  else if (existants.some(x => x.trim().toLowerCase() === nom.toLowerCase())) e.nom = 'Un persona porte déjà ce nom.'
  if (desc.length < 20) e.description_role = 'Décrivez qui pose la question et dans quelle situation (une phrase au moins).'
  else if (desc.length > 2000) e.description_role = '2 000 caractères au plus.'
  return e
}

export function nomFichierExport(collection: string, runId: string, format: 'json' | 'csv'): string {
  return `${collection}-questions-${runId.slice(0, 8)}.${format}`
}

/** Le résumé des relectures d'une liste de paires : { brut, valide, rejete }. */
export function bilanRelecture(paires: Pick<Paire, 'relecture'>[]): Record<'brut' | 'valide' | 'rejete', number> {
  const b = { brut: 0, valide: 0, rejete: 0 }
  for (const p of paires) if (p.relecture in b) b[p.relecture]++
  return b
}

export const AIDE_CONTEXTE = "Un persona, c'est la personne qui interroge la collection et la situation dans laquelle "
  + "elle le fait : son métier, à qui elle répond, ce qu'elle cherche à savoir. Les questions générées sont celles "
  + "qu'elle poserait ; les réponses de référence viennent des documents de la collection."

export const EXEMPLES_PERSONAS = [
  { nom: 'Agent au guichet étrangers', description_role: "Agent de préfecture au guichet étrangers. Répond à un usager qui demande où en est son dossier de titre de séjour et quelles pièces fournir." },
  { nom: 'Gestionnaire RH de proximité', description_role: "Gestionnaire des ressources humaines dans un service déconcentré. Répond à un agent qui s'interroge sur sa mobilité, ses congés ou sa rémunération." },
  { nom: 'Agent du support informatique', description_role: "Technicien du support informatique du ministère. Aide un agent qui ne peut plus se connecter, cherche un logiciel ou signale une panne de poste." },
]

/** Le persona créé d'office quand la génération de l'assistant part sans aucun persona. */
export const PERSONNA_DEFAUT = {
  nom: 'Lecteur des documents',
  description_role: 'Personne qui consulte la collection pour la première fois et cherche une information précise que contiennent ses documents.',
}

/** Une question du jeu de test d'évaluation (format historique de l'étape 4 de l'assistant). */
export interface QuestionEval {
  id: string
  question: string
  expected_answer: string
  must_cite: string[]
  tags: string[]
  out_of_scope?: boolean
  note?: string
}

export interface JeuEval { name: string, description: string, questions: QuestionEval[] }

/** Questions hors-sujet ajoutées à tout jeu généré : vérifient que le RAG refuse
 *  de fabriquer une réponse quand le sujet n'est pas couvert. */
export const HORS_SUJET: QuestionEval[] = [
  {
    id: 'hors-sujet-1',
    question: "Quel est l'age du capitaine ?",
    expected_answer: '',
    must_cite: [],
    tags: ['hors-sujet'],
    out_of_scope: true,
    note: 'Question hors-sujet pour verifier que le RAG ne fabrique pas de reponse.',
  },
  {
    id: 'hors-sujet-2',
    question: 'Quelle est la capitale de la Mongolie ?',
    expected_answer: '',
    must_cite: [],
    tags: ['hors-sujet'],
    out_of_scope: true,
    note: 'Question hors-sujet pour verifier que le RAG ne fabrique pas de reponse.',
  },
]

/** Le jeu de test d'évaluation tiré des paires d'un run : chaque paire non rejetée
 *  devient une question avec sa réponse de référence, complétée des hors-sujet. */
export function pairesVersJeu(
  paires: Pick<Paire, 'id' | 'question' | 'reponse' | 'persona' | 'relecture'>[],
  collection: string,
): JeuEval {
  const questions = paires
    .filter(p => p.relecture !== 'rejete')
    .map(p => ({
      id: p.id,
      question: p.question,
      expected_answer: p.reponse,
      must_cite: [],
      tags: [p.persona],
    }))
  return {
    name: `${collection}-evaluation`,
    description: 'Jeu de test genere automatiquement',
    questions: [...questions, ...HORS_SUJET],
  }
}

/** Un persona que l'on peut cocher pour une génération : déjà dans la collection (`id`), ou à créer. */
export interface CandidatPersona {
  cle: string
  id?: string
  nom: string
  description_role: string
  origine: 'collection' | 'exemple' | 'proposition' | 'libre'
  coche: boolean
}

export const PERSONAS_MAX = 5

const plier = (s: string) => (s || '').trim().toLowerCase()

/**
 * Les candidats, sans doublon de nom (à la casse près) : ceux de la collection d'abord, puis
 * les propositions tirées des documents, puis les exemples. Les deux premiers de la collection
 * sont cochés d'office ; sans persona dans la collection, le premier exemple l'est.
 */
export function candidatsInitiaux(existants: { id: string, nom: string, description_role: string }[],
  exemples: { nom: string, description_role: string }[]): CandidatPersona[] {
  const vus = new Set<string>()
  const liste: CandidatPersona[] = []
  for (const p of existants) {
    if (vus.has(plier(p.nom))) continue
    vus.add(plier(p.nom))
    liste.push({ cle: `id:${p.id}`, id: p.id, nom: p.nom, description_role: p.description_role, origine: 'collection', coche: liste.length < 2 })
  }
  for (const e of exemples) {
    if (vus.has(plier(e.nom))) continue
    vus.add(plier(e.nom))
    liste.push({ cle: `ex:${plier(e.nom)}`, nom: e.nom, description_role: e.description_role, origine: 'exemple', coche: !existants.length && liste.length === 0 })
  }
  return liste
}

/** Ajoute des candidats (propositions, persona libre) en tête de la liste ; un nom déjà présent est ignoré.
 *  Rend le nombre de candidats réellement ajoutés. Ils arrivent cochés tant qu'il reste de la place. */
export function ajouterCandidats(liste: CandidatPersona[], nouveaux: { nom: string, description_role: string }[],
  origine: 'proposition' | 'libre'): number {
  const vus = new Set(liste.map(c => plier(c.nom)))
  let n = 0
  const ajout: CandidatPersona[] = []
  for (const p of nouveaux) {
    if (!plier(p.nom) || vus.has(plier(p.nom))) continue
    vus.add(plier(p.nom))
    ajout.push({ cle: `${origine}:${plier(p.nom)}`, nom: p.nom.trim(), description_role: p.description_role.trim(), origine, coche: false })
    n++
  }
  liste.unshift(...ajout)
  let place = PERSONAS_MAX - liste.filter(c => c.coche).length
  for (const c of ajout) if (place > 0) { c.coche = true; place-- }
  return n
}

/** Ce qu'il faut faire avant de lancer : les ids à reprendre, les personas à créer (validés). */
export function preparerLancement(liste: CandidatPersona[]): { ids: string[], aCreer: { nom: string, description_role: string }[], erreur: string } {
  const coches = liste.filter(c => c.coche)
  if (!coches.length) return { ids: [], aCreer: [], erreur: 'Cochez au moins un persona.' }
  if (coches.length > PERSONAS_MAX) return { ids: [], aCreer: [], erreur: `${PERSONAS_MAX} personas au plus par génération.` }
  const noms = liste.filter(c => c.origine === 'collection').map(c => c.nom)
  for (const c of coches.filter(x => !x.id)) {
    const e = validerPersona(c, noms)
    if (e.nom || e.description_role) return { ids: [], aCreer: [], erreur: `« ${c.nom || 'Persona sans nom'} » : ${e.nom || e.description_role}` }
  }
  return {
    ids: coches.filter(c => c.id).map(c => c.id!),
    aCreer: coches.filter(c => !c.id).map(c => ({ nom: c.nom.trim(), description_role: c.description_role.trim() })),
    erreur: '',
  }
}
