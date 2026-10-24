/**
 * Résana à l'écran (docs/resana.md) : lire les erreurs du service, dire où en est un import ou une
 * synchronisation. Fonctions pures, testées dans tests/unit/resana.test.ts.
 */

export interface ErreurResana {
  message: string
  code?: string
  /** La page de connexion à Résana que donne le service (https seulement). */
  urlConnexion?: string
  reessayable?: boolean
}

export interface TravailResana {
  etat?: 'en_cours' | 'termine' | 'a_jour' | 'partiel' | 'echec' | 'interrompu' | string
  action?: 'import' | 'synchronisation' | string
  /** En cours : le service prépare la liste d'un grand dossier, ou les documents arrivent. */
  phase?: 'preparation' | 'telechargement' | string
  dossiers_lus?: number | null
  dossiers?: number | null
  total?: number
  faits?: number
  ajoutes?: number
  modifies?: number
  retires?: number
  inchanges?: number
  ecartes?: number
  /** Documents qu'OpenRAG n'a pas su lire (PDF sans texte, délai dépassé). */
  en_erreur?: number
  /** Vérification complète : chaque document retéléchargé pour comparer son empreinte. */
  complet?: boolean
  message?: string
  code?: string
  url_connexion?: string
  documents_ecartes?: { titre: string, raison: string }[]
}

export interface StatutResana {
  configured: boolean
  espace_nom?: string | null
  dossier_chemin?: string | null
  documents: number
  last_sync_at?: string | null
  travail?: TravailResana | null
  est_importeur: boolean
}

const ERREUR_API = /^API error (\d+): (.*)$/s
const REPLI = 'Le service Résana ne répond pas comme prévu. Réessayez dans un instant.'

function lienSur (url: unknown): string | undefined {
  return typeof url === 'string' && url.startsWith('https://') ? url : undefined
}

/** L'erreur levée par useApi (« API error 409: {…} »), en phrase et lien de connexion. */
export function erreurResana (brut: unknown): ErreurResana {
  const texte = brut instanceof Error ? brut.message : String(brut ?? '')
  const m = ERREUR_API.exec(texte)
  if (!m) {
    return { message: REPLI, reessayable: true }
  }
  const statut = Number(m[1])
  let detail: unknown
  try {
    detail = (JSON.parse(m[2] ?? '') as { detail?: unknown }).detail
  }
  catch {
    return { message: REPLI, reessayable: statut >= 500 }
  }
  if (typeof detail === 'string') {
    return { message: detail, reessayable: statut >= 500 }
  }
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>
    return {
      message: typeof d.message === 'string' && d.message ? d.message : REPLI,
      code: typeof d.code === 'string' ? d.code : undefined,
      urlConnexion: lienSur(d.url_connexion),
      reessayable: d.reessayable === true,
    }
  }
  return { message: REPLI, reessayable: statut >= 500 }
}

function compte (n: number | undefined, un: string, plusieurs: string): string {
  const v = n ?? 0
  return `${v} ${v > 1 ? plusieurs : un}`
}

/** Une phrase sur l'import ou la synchronisation en cours ou finie. */
export function libelleTravail (t: TravailResana | null | undefined): string {
  if (!t || !t.etat) {
    return ''
  }
  const feminin = t.action === 'synchronisation'
  const quoi = feminin ? 'Synchronisation' : 'Import'
  const e = feminin ? 'e' : ''
  switch (t.etat) {
    case 'en_cours':
      if (t.phase === 'preparation') {
        return `Résana prépare la liste du dossier${preparation(t.dossiers_lus, t.dossiers)}. Un grand dossier peut demander plusieurs minutes.`
      }
      if (t.phase === 'indexation') {
        return `Indexation en cours : ${t.faits ?? 0} sur ${compte(t.total, 'document', 'documents')} confiés au moteur de recherche, quelques-uns à la fois.`
      }
      return t.total ? `${quoi} en cours : ${t.faits ?? 0} sur ${compte(t.total, 'document', 'documents')} lus.` : `${quoi} en cours : rien à télécharger, Résana annonce les mêmes versions.`
    case 'a_jour':
      return 'Rien n\'a changé dans Résana depuis la dernière synchronisation.'
    case 'termine': {
      const parties = [
        compte(t.ajoutes, 'ajouté', 'ajoutés'),
        compte(t.modifies, 'modifié', 'modifiés'),
        compte(t.retires, 'retiré', 'retirés'),
      ]
      const ecartes = t.ecartes ? `, ${compte(t.ecartes, 'écarté', 'écartés')}` : ''
      const erreurs = t.en_erreur ? ` ${compte(t.en_erreur, 'document n\'a', 'documents n\'ont')} pas pu être lu${t.en_erreur > 1 ? 's' : ''} par le moteur de recherche.` : ''
      return `${quoi} terminé${e} : ${parties.join(', ')}${ecartes}.${erreurs}`
    }
    case 'partiel': {
      const recus = (t.ajoutes ?? 0) + (t.modifies ?? 0)
      return `${quoi} arrêté${e} en route : ${t.message || 'erreur du service Résana.'} ${compte(recus, 'document reçu est gardé', 'documents reçus sont gardés')} ; synchronisez de nouveau pour continuer.`
    }
    case 'interrompu':
      return `${quoi} interrompu${e} (le service a redémarré). Relancez la synchronisation.`
    case 'echec':
      return `${quoi} arrêté${e} : ${t.message || 'erreur du service Résana.'}`
    default:
      return ''
  }
}

export function travailEnCours (t: TravailResana | null | undefined): boolean {
  // « partiel » est fini : la personne relance quand sa session est rouverte.
  return t?.etat === 'en_cours'
}

/** « : 12 dossiers lus sur 40 », ou rien si le service ne le dit pas. */
export function preparation (lus: number | null | undefined, total: number | null | undefined): string {
  if (typeof lus !== 'number' || typeof total !== 'number' || !total) {
    return ''
  }
  return ` : ${lus} dossier${lus > 1 ? 's' : ''} lu${lus > 1 ? 's' : ''} sur ${total}`
}

/** « 40 documents, environ 120 Mo » — la taille de Résana est arrondie, on le dit. */
export function resumeApercu (a: { total: number, taille_approx_mo?: number | null }): string {
  const docs = compte(a.total, 'document', 'documents')
  if (typeof a.taille_approx_mo !== 'number') {
    return docs
  }
  const mo = a.taille_approx_mo < 1 ? 'moins de 1 Mo' : `environ ${Math.round(a.taille_approx_mo)} Mo`
  return `${docs}, ${mo}`
}

// ─── Le périmètre : quels sous-dossiers indexer ─────────────────────────────────────────────

/** Un sous-dossier du dossier choisi, avec ses comptes (route `/inventaire`). */
export interface NoeudResana {
  id: string
  titre: string
  parent_id: string | null
  profondeur: number
  /** Documents rangés directement dans ce dossier. */
  documents: number
  /** Documents de tout son sous-arbre. */
  documents_total: number
  taille_approx_mo?: number | null
}

export interface InventaireResana {
  total: number
  taille_approx_mo?: number | null
  documents_a_la_racine: number
  dossiers: NoeudResana[]
}

/** Exclu de lui-même ou par un dossier parent exclu. */
export function estExclu (id: string, exclus: ReadonlySet<string>, noeuds: readonly NoeudResana[]): boolean {
  const parents = new Map(noeuds.map(n => [n.id, n.parent_id]))
  let courant: string | null | undefined = id
  const vus = new Set<string>()
  while (courant && !vus.has(courant)) {
    if (exclus.has(courant)) {
      return true
    }
    vus.add(courant)
    courant = parents.get(courant)
  }
  return false
}

/** Exclu par un parent : sa case est grisée (on ne réinclut pas un dossier dans un dossier exclu). */
export function exclusParUnParent (n: NoeudResana, exclus: ReadonlySet<string>, noeuds: readonly NoeudResana[]): boolean {
  return !!n.parent_id && estExclu(n.parent_id, exclus, noeuds)
}

/**
 * Cocher ou décocher un dossier. Décocher l'exclut avec tout son contenu ; les exclusions plus
 * fines sous lui deviennent inutiles et sont retirées, pour que la liste reste la plus courte.
 */
export function basculer (id: string, exclus: ReadonlySet<string>, noeuds: readonly NoeudResana[]): Set<string> {
  const suivant = new Set(exclus)
  if (suivant.has(id)) {
    suivant.delete(id)
    return suivant
  }
  suivant.add(id)
  for (const autre of [...suivant]) {
    if (autre !== id && estExclu(autre, new Set([id]), noeuds)) {
      suivant.delete(autre)
    }
  }
  return suivant
}

/** Ce que la sélection indexera : documents et dossiers retenus. */
export function selection (inv: InventaireResana, exclus: ReadonlySet<string>): { documents: number, dossiers: number } {
  let documents = inv.documents_a_la_racine
  let dossiers = 0
  for (const n of inv.dossiers) {
    if (!estExclu(n.id, exclus, inv.dossiers)) {
      documents += n.documents
      dossiers += 1
    }
  }
  return { documents, dossiers }
}

/** Le résumé de couverture d'une collection Résana (`source_resume`, ou l'état de `/status`). */
export interface CouvertureResana {
  couverture: 'totale' | 'partielle' | string
  raisons?: string[]
  documents_indexes?: number
  documents_perimetre?: number | null
  documents_disponibles?: number | null
}

/** L'étiquette des listes : « Résana · index complet » ou « Résana · index partiel ». */
export function etiquetteResana (c: CouvertureResana | null | undefined): string {
  if (!c) {
    return ''
  }
  return c.couverture === 'totale' ? 'Résana · index complet' : 'Résana · index partiel'
}

/** La phrase qui explique la couverture : ce qui est indexé, sur quoi, et pourquoi c'est partiel. */
export function phraseCouverture (c: CouvertureResana | null | undefined): string {
  if (!c) {
    return ''
  }
  const indexes = c.documents_indexes ?? 0
  const sur = typeof c.documents_disponibles === 'number' ? ` sur ${c.documents_disponibles} dans le dossier Résana` : ''
  const base = `${indexes} document${indexes > 1 ? 's' : ''} indexé${indexes > 1 ? 's' : ''}${sur}`
  const raisons = c.raisons || []
  if (c.couverture === 'totale') {
    return `${base} : index complet du dossier.`
  }
  const pourquoi: string[] = []
  if (raisons.includes('selection')) {
    pourquoi.push('certains sous-dossiers sont exclus')
  }
  if (raisons.includes('interrompue')) {
    pourquoi.push('la dernière mise à jour s\'est arrêtée en route')
  }
  if (raisons.includes('a_faire')) {
    pourquoi.push('l\'indexation n\'a pas encore eu lieu')
  }
  return `${base} : index partiel${pourquoi.length ? ` (${pourquoi.join(', ')})` : ''}.`
}

/** L'invitation à mettre l'index à jour, glissée dans une réponse (champ `avis`). */
export interface AvisResana {
  collection: string
  /** Le titre de la collection, déjà repris dans `message`. */
  titre?: string
  code: string
  message: string
  action: { libelle: string, url: string }
}

/** Les avis lisibles d'une réponse : une liste d'objets complets, sinon rien. Un lien externe est écarté. */
export function avisDeReponse (brut: unknown): AvisResana[] {
  if (!Array.isArray(brut)) {
    return []
  }
  return brut.filter((a): a is AvisResana => !!a && typeof a === 'object'
    && typeof (a as AvisResana).message === 'string'
    && typeof (a as AvisResana).action?.url === 'string'
    && (a as AvisResana).action.url.startsWith('/')
    && !(a as AvisResana).action.url.startsWith('//'))
}

/** La fiche proposée pour un dossier Résana : titre et description déjà écrits, à relire. */
export function ficheDepuisResana (d: { titre: string, chemin: string }, espaceNom: string): { titre: string, description: string } {
  const titre = (d.titre || d.chemin.split(' / ').pop() || 'Dossier Résana').trim()
  const ou = d.chemin && d.chemin !== titre ? ` (${d.chemin})` : ''
  return {
    titre,
    description: `Les documents du dossier « ${titre} »${ou} de l'espace Résana « ${espaceNom} ».`,
  }
}
