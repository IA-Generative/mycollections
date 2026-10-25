/**
 * L'assistant de création d'une collection (refonte du 2026-10-19) : ses étapes, ses sources,
 * les réglages avancés de l'étape 2 et l'identifiant proposé. Fonctions pures, testées dans
 * tests/unit/wizard.test.ts.
 */
import type { Capacites, Drapeau } from './capacites'
import type { ReglesNommage } from './collectionName'
import { deriverIdentifiant, motifRefus, REGLES_PAR_DEFAUT } from './collectionName'

/** Les cinq étapes, dans l'ordre. « Partage » est aussi le libellé de l'accueil et de /admin. */
export const ETAPES_ASSISTANT = ['Source', 'Identification', 'Documents', 'Vérifier les réponses', 'Partage'] as const

/** Le libellé de l'étape qui suit l'étape `n` (numérotée de 1 à 5), ou null après la dernière. */
export function etapeSuivante (n: number): string | null {
  return ETAPES_ASSISTANT[n] ?? null
}

/** « source, identification, documents, vérifier les réponses, partage ». */
export function etapesEnPhrase (): string {
  return ETAPES_ASSISTANT.map(e => e.toLowerCase()).join(', ')
}

/**
 * L'adresse des étapes 3 à 5 pour une collection créée. Une collection Résana a sa propre étape 3
 * (le suivi de l'indexation, dans `admin/create/resana`) et garde `source=resana` jusqu'au bout :
 * l'étape 5 sait ainsi qu'elle ne se partage pas (règle v1, docs/resana.md).
 */
export function lienEtape (numero: 3 | 4 | 5, collection: string, source = ''): string {
  const c = encodeURIComponent(collection)
  if (source === 'resana') {
    return numero === 3 ? `/admin/create/resana?collection=${c}` : `/admin/create/step-${numero}?collection=${c}&source=resana`
  }
  return `/admin/create/step-${numero}?collection=${c}`
}

export interface Source {
  cle: string
  nom: string
  /** Le nom dans la ligne « Bientôt : … ». */
  court: string
  description: string
  icone: string
  /** Vrai seulement si le code sait traiter cette source de bout en bout. */
  disponible: boolean
  miseAJourAuto?: boolean
  /** Branchée mais gardée par une capacité : disponible seulement si ce drapeau est allumé. */
  drapeau?: Drapeau
}

/** Les sources, dans l'ordre d'affichage. Une source devient une carte quand elle est branchée. */
export const SOURCES: readonly Source[] = [
  { cle: 'file', nom: 'Un fichier', court: 'un fichier', icone: 'fr-icon-file-line', disponible: true, description: 'PDF, Word, texte… depuis votre poste ou une adresse web.' },
  { cle: 'directory', nom: 'Un dossier de votre poste', court: 'un dossier', icone: 'fr-icon-folder-2-line', disponible: true, description: 'Tout un dossier, sous-dossiers compris.' },
  { cle: 'legifrance', nom: 'Légifrance', court: 'Légifrance', icone: 'fr-icon-scales-3-line', disponible: false, miseAJourAuto: true, description: 'Un code ou une loi, découpé par article.' },
  { cle: 'drive', nom: 'Un dossier Drive', court: 'Drive', icone: 'fr-icon-cloud-line', disponible: false, miseAJourAuto: true, description: 'Un dossier de la Suite numérique, réindexé quand son contenu change.' },
  { cle: 'nextcloud', nom: 'Nextcloud', court: 'Nextcloud', icone: 'fr-icon-cloud-line', disponible: false, miseAJourAuto: true, description: 'Un dossier Nextcloud, réindexé quand il change.' },
  { cle: 'resana', nom: 'Un dossier Résana', court: 'Résana', icone: 'fr-icon-team-line', disponible: false, drapeau: 'resana', description: 'Un dossier de vos espaces, lu avec vos droits. Reste privée.' },
  { cle: 'website', nom: 'Une page ou un site', court: 'un site web', icone: 'fr-icon-global-line', disponible: false, miseAJourAuto: true, description: 'Une adresse web, relue et découpée page par page.' },
  { cle: 'mcp', nom: 'Un outil MCP', court: 'un outil MCP', icone: 'fr-icon-links-line', disponible: false, description: 'Les ressources d\'un serveur MCP, comme documents.' },
]

/** Les sources selon les capacités : une source gardée par un drapeau allumé devient disponible. */
export function sourcesSelon (capacites: Capacites, sources: readonly Source[] = SOURCES): Source[] {
  return sources.map(s => (s.drapeau && capacites[s.drapeau] === true ? { ...s, disponible: true } : s))
}

/** Les sources que l'on peut choisir : une carte chacune. */
export function cartesDeSource (sources: readonly Source[] = SOURCES): Source[] {
  return sources.filter(s => s.disponible)
}

/** « Bientôt : Légifrance, Drive, … » — les autres sources, sans promesse de date. Vide s'il n'y en a pas. */
export function ligneBientot (sources: readonly Source[] = SOURCES): string {
  const autres = sources.filter(s => !s.disponible).map(s => s.court)
  return autres.length ? `Bientôt : ${autres.join(', ')}.` : ''
}

/**
 * Les réglages avancés de l'étape 2 et leur valeur par défaut. Le type de collection (profil)
 *  dépend de la source : un dossier est d'emblée un corpus de plusieurs documents.
 */
export interface ReglagesAvances {
  profil: string
  sensitivity: string
  graph_enabled: boolean
  ai_summary_enabled: boolean
  /** L'identifiant a été modifié à la main (il ne suit plus le titre). */
  identifiant_manuel: boolean
}

export const REGLAGES_AVANCES_DEFAUT: ReglagesAvances = {
  profil: 'generique',
  sensitivity: 'public',
  graph_enabled: false,
  ai_summary_enabled: false,
  identifiant_manuel: false,
}

const TIRETS_FINAUX = /-+$/
const PROFIL_PAR_SOURCE: Record<string, string> = { directory: 'corpus', drive: 'corpus', nextcloud: 'corpus', resana: 'corpus', legifrance: 'juridique' }

export function reglagesAvancesDefaut (source: string): ReglagesAvances {
  return { ...REGLAGES_AVANCES_DEFAUT, profil: PROFIL_PAR_SOURCE[source] || REGLAGES_AVANCES_DEFAUT.profil }
}

/** Les champs du formulaire rangés dans le repli « Réglages avancés ». */
export const CHAMPS_AVANCES = ['profil', 'sensitivity', 'graph_enabled', 'ai_summary_enabled', 'name'] as const

/**
 * Le repli « Réglages avancés (facultatif) » reste-t-il replié ? Oui aux valeurs par défaut ; non
 * dès qu'une valeur en diffère (on ne cache pas un choix fait), ou qu'un de ses champs porte une
 * erreur (on ne cache pas ce qui bloque).
 */
export function replierReglagesAvances (
  form: Partial<ReglagesAvances>,
  erreurs: Partial<Record<string, string | null | undefined>>,
  defaut: ReglagesAvances = REGLAGES_AVANCES_DEFAUT,
): boolean {
  if (CHAMPS_AVANCES.some(c => !!erreurs[c])) {
    return false
  }
  return (Object.keys(defaut) as (keyof ReglagesAvances)[]).every(k => form[k] === undefined || form[k] === defaut[k])
}

/**
 * L'identifiant proposé d'après le titre ; s'il est pris, le premier suffixe libre (« -2 », « -3 »…),
 * en raccourcissant la base pour rester dans la longueur permise. Rend '' si le titre ne donne rien
 * d'acceptable.
 */
export function identifiantPropose (titre: string, pris: ReadonlySet<string> | readonly string[], regles: ReglesNommage = REGLES_PAR_DEFAUT): string {
  const dejaPris = pris instanceof Set ? pris : new Set(pris as readonly string[])
  const base = deriverIdentifiant(titre, regles.max, regles.prefixe_impose || '')
  if (!base) {
    return ''
  }
  const acceptable = (x: string) => !motifRefus(x, regles) && !dejaPris.has(x)
  if (acceptable(base)) {
    return base
  }
  for (let n = 2; n < 100; n++) {
    const suffixe = `-${n}`
    const racine = base.slice(0, regles.max - suffixe.length).replace(TIRETS_FINAUX, '')
    const candidat = `${racine}${suffixe}`
    if (acceptable(candidat)) {
      return candidat
    }
  }
  return ''
}

// ─── Étape 4 : le test technique ────────────────────────────────────────────

/** Trois questions au plus : au-delà, c'est le travail de la page Qualité. */
export const NB_QUESTIONS_TEST = 3

/** Les questions proposées par le serveur, nettoyées : sans vide ni doublon, trois au plus. */
export function questionsSuggerees (brut: unknown): string[] {
  const liste = Array.isArray((brut as { questions?: unknown })?.questions) ? (brut as { questions: unknown[] }).questions : []
  const propres = liste.filter((q): q is string => typeof q === 'string').map(q => q.trim()).filter(q => q.length >= 3)
  return [...new Set(propres)].slice(0, NB_QUESTIONS_TEST)
}

/**
 * Les questions de l'étape 4 une fois les suggestions arrivées : une suggestion ne remplit qu'une
 * case vide. Les suggestions arrivent après l'affichage ; ce que la personne a déjà tapé reste.
 */
export function completerQuestions (actuelles: readonly string[], suggestions: readonly string[]): string[] {
  return actuelles.map((q, i) => (q.trim() ? q : (suggestions[i] ?? q)))
}

export type CleVerdict = 'repond' | 'ne_repond_pas'

export interface VerdictTechnique { cle: CleVerdict, libelle: string, aide?: string }

const REFUS = /je ne (?:sais|trouve|dispose)|aucune information|pas d'information|ne contiennent? pas|ne (?:me )?permet(?:tent)? pas de r[ée]pondre/i

/**
 * Le verdict simple de l'étape 4 : la collection « répond » si elle rend un texte, appuyé sur au
 * moins un passage, qui n'est pas un refus. Pas de juge, pas de note : c'est un test technique
 * (le document est-il lu, découpé, retrouvé ?) ; la qualité se mesure ensuite dans la page Qualité.
 */
export function verdictTechnique (r: { response?: string, source_names?: string[], sources?: unknown[] } | null | undefined): VerdictTechnique {
  const texte = (r?.response || '').trim()
  const passages = r?.source_names?.length || r?.sources?.length || 0
  if (texte && passages > 0 && !REFUS.test(texte)) {
    return { cle: 'repond', libelle: 'La collection répond' }
  }
  return {
    cle: 'ne_repond_pas',
    libelle: 'La collection ne répond pas',
    aide: passages ? 'Elle a trouvé des passages sans pouvoir répondre : la question sort peut-être de son contenu.' : 'Aucun passage trouvé : l\'indexation est peut-être encore en cours, réessayez dans une minute.',
  }
}

/**
 * Le corps qui fait entrer une question posée au test dans le jeu de questions, « à relire » :
 *  sans réponse de référence (celle de la collection n'en est pas une). Rien si elle est trop courte.
 */
export function chargeAuJeu (question: string): { question: string, relecture: 'brut' } | null {
  const q = (question || '').trim()
  return q.length >= 3 ? { question: q, relecture: 'brut' } : null
}

const DIACRITIQUES = /[\u0300-\u036F]/g
const NON_MOT = /[^\p{L}\p{N}_]+/gu
const ESPACES = /\s+/g

/** Une question comparable (même règle que `questions_store.plier` côté serveur). */
export function plierQuestion (texte: string): string {
  return (texte || '').normalize('NFD').replace(DIACRITIQUES, '').toLowerCase().replace(NON_MOT, ' ').trim().replace(ESPACES, ' ')
}

/** La fiche du jeu qui porte cette question (accents, casse et ponctuation ignorés), ou null. */
export function trouverQuestion<T extends { question: string }> (liste: readonly T[], texte: string): T | null {
  const voulu = plierQuestion(texte)
  return liste.find(q => plierQuestion(q.question) === voulu) || null
}

export type Validation = 'oui' | 'non' | null

/**
 * Le bilan de l'étape 4 : combien de questions posées, combien de réponses jugées bonnes ou
 * insuffisantes par la personne, combien sans avis — en une phrase. « Étape suivante » ne dépend
 * pas du bilan : il informe, il ne bloque pas.
 */
export function bilanVerification (essais: readonly { verdict: VerdictTechnique | null, validation: Validation }[]): { posees: number, repondent: number, oui: number, non: number, sansAvis: number, phrase: string } {
  const posees = essais.filter(e => e.verdict)
  const repondent = posees.filter(e => e.verdict?.cle === 'repond').length
  const oui = posees.filter(e => e.validation === 'oui').length
  const non = posees.filter(e => e.validation === 'non').length
  const sansAvis = posees.length - oui - non
  const n = posees.length
  if (!n) {
    return { posees: 0, repondent: 0, oui: 0, non: 0, sansAvis: 0, phrase: 'Vous n\'avez posé aucune question. Vous pourrez le faire à tout moment depuis la fiche de la collection.' }
  }
  const s = (k: number) => (k > 1 ? 's' : '')
  const parts = [`${oui} réponse${s(oui)} jugée${s(oui)} bonne${s(oui)}`, `${non} insuffisante${s(non)}`, `${sansAvis} sans avis`]
  return { posees: n, repondent, oui, non, sansAvis, phrase: `${n} question${s(n)} posée${s(n)} : ${parts.join(', ')}. Tout est dans le jeu de questions de la collection.` }
}
