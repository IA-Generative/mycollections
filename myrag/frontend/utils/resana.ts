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

// ─── Le périmètre : les dossiers inclus, cochés dans l'arbre de l'espace ─────────────────────

/** Un dossier de l'espace (route `/espaces/{id}/dossiers`). */
export interface DossierResana {
  id: string
  titre: string
  parent_id: string | null
  chemin: string
}

/** Un espace Résana et sa fiche d'identité (champs facultatifs, selon le service). */
export interface EspaceResana {
  id: string
  nom: string
  description?: string
  objet?: string
}

const DIACRITIQUES = /[\u0300-\u036F]/g

function sansAccents (s: string): string {
  return s.normalize('NFD').replace(DIACRITIQUES, '').toLowerCase()
}

/** Les espaces dont le nom, l'objet ou la description contient la recherche (accents ignorés). */
export function filtrerEspaces (espaces: readonly EspaceResana[], recherche: string): EspaceResana[] {
  const q = sansAccents(recherche.trim())
  if (!q) {
    return [...espaces]
  }
  return espaces.filter(e => sansAccents(`${e.nom} ${e.objet || ''} ${e.description || ''}`).includes(q))
}

/** {parent: enfants} et la liste des racines (dossiers dont le parent n'est pas dans la liste). */
export function arbreDossiers (dossiers: readonly DossierResana[]): { enfants: Map<string | null, DossierResana[]>, racines: DossierResana[] } {
  const ids = new Set(dossiers.map(d => d.id))
  const enfants = new Map<string | null, DossierResana[]>()
  const racines: DossierResana[] = []
  for (const d of dossiers) {
    const parent = d.parent_id && ids.has(d.parent_id) ? d.parent_id : null
    if (parent === null) {
      racines.push(d)
    }
    enfants.set(parent, [...(enfants.get(parent) || []), d])
  }
  const parTitre = (a: DossierResana, b: DossierResana) => a.titre.localeCompare(b.titre, 'fr')
  for (const liste of enfants.values()) {
    liste.sort(parTitre)
  }
  return { enfants, racines: racines.sort(parTitre) }
}

/** Les ancêtres d'un dossier, du parent à la racine. */
export function ancetres (id: string, dossiers: readonly DossierResana[]): string[] {
  const parents = new Map(dossiers.map(d => [d.id, d.parent_id]))
  const rendu: string[] = []
  let p = parents.get(id) ?? null
  while (p && parents.has(p) && !rendu.includes(p)) {
    rendu.push(p)
    p = parents.get(p) ?? null
  }
  return rendu
}

/** Coché par un dossier parent : il est déjà inclus (case cochée et grisée). */
export function inclusParUnParent (id: string, choisis: ReadonlySet<string>, dossiers: readonly DossierResana[]): boolean {
  return ancetres(id, dossiers).some(a => choisis.has(a))
}

/**
 * Cocher ou décocher un dossier. Cocher un dossier inclut tout son contenu : les sous-dossiers déjà
 * cochés deviennent redondants et sont retirés, pour que la liste reste la plus courte.
 */
export function basculerDossier (id: string, choisis: ReadonlySet<string>, dossiers: readonly DossierResana[]): Set<string> {
  const suivant = new Set(choisis)
  if (suivant.has(id)) {
    suivant.delete(id)
    return suivant
  }
  suivant.add(id)
  for (const autre of [...suivant]) {
    if (autre !== id && ancetres(autre, dossiers).includes(id)) {
      suivant.delete(autre)
    }
  }
  return suivant
}

/** Les dossiers à montrer pour une recherche : ceux qui correspondent, et leurs ancêtres (pour le contexte). */
export function dossiersVisibles (dossiers: readonly DossierResana[], recherche: string): Set<string> | null {
  const q = sansAccents(recherche.trim())
  if (!q) {
    return null
  }
  const rendu = new Set<string>()
  for (const d of dossiers) {
    if (sansAccents(`${d.titre} ${d.chemin}`).includes(q)) {
      rendu.add(d.id)
      for (const a of ancetres(d.id, dossiers)) {
        rendu.add(a)
      }
    }
  }
  return rendu
}

/** Le résumé de couverture d'une collection Résana (`source_resume`, ou l'état de `/status`). */
export interface CouvertureResana {
  couverture: 'totale' | 'partielle' | string
  espace_nom?: string | null
  entite?: string | null
  nb_dossiers?: number
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
  const sur = typeof c.documents_disponibles === 'number' ? ` sur ${c.documents_disponibles} dans les dossiers choisis` : ''
  const base = `${indexes} document${indexes > 1 ? 's' : ''} indexé${indexes > 1 ? 's' : ''}${sur}`
  const raisons = c.raisons || []
  if (c.couverture === 'totale') {
    return `${base} : index complet.`
  }
  const pourquoi: string[] = []
  if (raisons.includes('selection')) {
    pourquoi.push('certains sous-dossiers sont exclus')
  }
  if (raisons.includes('interrompue')) {
    pourquoi.push('la dernière mise à jour s\'est arrêtée en route')
  }
  if (raisons.includes('a_faire')) {
    pourquoi.push('rien n\'est encore indexé')
  }
  if (raisons.includes('erreurs_de_lecture')) {
    pourquoi.push('le moteur n\'a pas su lire certains documents')
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

/** Le titre proposé pour une collection ancrée sur un espace : le nom de l'espace. */
export function titreDepuisEspace (espace: EspaceResana): string {
  return (espace.nom || `Espace Résana ${espace.id}`).trim()
}

/** La description que le serveur posera si on n'en écrit pas (aperçu dans le champ). */
export function descriptionParDefaut (espace: EspaceResana, entite: string): string {
  const e = entite.trim() ? `, ${entite.trim()}` : ''
  return `Espace Résana « ${espace.nom || espace.id} » (n° ${espace.id})${e}.`
}

/**
 * Une collection Résana se remplit par sa sélection de dossiers, découpée par l'indexeur : sa page
 * « Gérer les documents » n'a ni dépôt de fichiers ni choix du découpage (#134). Un fichier déposé
 * à la main se mêlerait à l'index Résana, sans source ni mise à jour.
 */
export function estCollectionResana (fiche: { source_type?: string | null } | null | undefined): boolean {
  return fiche?.source_type === 'resana'
}

/** Le titre de la page des documents d'une collection. */
export function titrePageDocuments (fiche: { source_type?: string | null } | null | undefined): string {
  return estCollectionResana(fiche) ? 'Gérer les documents' : 'Ajouter des documents'
}

/**
 * Ouvrir une collection Résana à un groupe (décision du 2026-10-24, docs/resana.md) : qui la gère
 * choisit le groupe et confirme que chacun de ses membres a accès, dans Résana, aux dossiers
 * indexés. Jamais à tout le monde. Même phrase dans l'assistant de création et dans « Partager ».
 */
export const CONFIRMATION_DROITS_RESANA = 'J\'ai vérifié que chaque membre de ce groupe a accès, dans Résana, aux dossiers indexés. C\'est moi qui pilote ce partage.'

/** Le partage d'une collection Résana peut partir : un groupe nommé et la confirmation cochée. */
export function partageResanaPret (groupe: string, confirme: boolean): boolean {
  return !!groupe.trim() && confirme
}
