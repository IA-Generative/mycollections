/**
 * La fiche d'une collection (refonte du 2026-10-19) : ce qu'elle offre selon les droits, ses
 * onglets, sa ligne de métadonnées et l'aperçu des consignes. Fonctions pures, testées dans
 * tests/unit/fiche.test.ts.
 */

export interface ActionFiche {
  cle: 'question' | 'partager' | 'documents' | 'reglages' | 'graphe'
  libelle: string
  vers: string
  icone: string
  /** Présente mais inactive (avec son explication dans `aide`). */
  desactivee?: boolean
  aide?: string
}

/**
 * Les gestes de la fiche : « Poser une question » pour tous, « Partager » pour qui gère ; le menu
 * Plus range Ajouter des documents et Réglages (pour qui gère) et les liens entre documents,
 * présents mais inactifs sans graphe.
 */
export function actionsFiche (droits: { ecrire?: boolean } | null | undefined, graphe: boolean, id: string): { principales: ActionFiche[], plus: ActionFiche[] } {
  const base = `/c/${encodeURIComponent(id)}`
  const gere = droits?.ecrire === true
  const principales: ActionFiche[] = [
    { cle: 'question', libelle: 'Poser une question', vers: `${base}/playground`, icone: 'fr-icon-chat-3-line' },
  ]
  if (gere) {
    principales.push({ cle: 'partager', libelle: 'Partager', vers: `${base}/publish`, icone: 'fr-icon-share-forward-line', aide: 'Rendre la collection disponible dans le chat MirAI, et choisir qui la voit.' })
  }
  const plus: ActionFiche[] = []
  if (gere) {
    plus.push(
      { cle: 'documents', libelle: 'Ajouter des documents', vers: `${base}/upload`, icone: 'fr-icon-file-add-line' },
      { cle: 'reglages', libelle: 'Réglages', vers: `${base}/config`, icone: 'fr-icon-settings-5-line' },
    )
  }
  plus.push({
    cle: 'graphe',
    libelle: 'Liens entre documents',
    vers: `${base}/graph`,
    icone: 'fr-icon-links-line',
    desactivee: !graphe,
    aide: graphe ? 'La carte des renvois entre documents.' : 'Disponible quand les liens entre documents sont activés dans les réglages.',
  })
  return { principales, plus }
}

export type CleOnglet = 'documents' | 'signalements' | 'propositions' | 'historique' | 'agent'

export interface OngletFiche { cle: CleOnglet, libelle: string }

function avecCompteur (libelle: string, n: number | null | undefined): string {
  return typeof n === 'number' ? `${libelle} (${n})` : libelle
}

/**
 * Les onglets de la fiche, dans l'ordre : Documents · Signalements · Propositions · Historique.
 *  Un compteur connu s'affiche dans le libellé. « Interroger avec un agent » s'y ajoute, en
 *  dernier, seulement quand Mes agents est branché.
 */
export function ongletsFiche (
  compteurs: { documents?: number | null, signalements?: number | null, propositions?: number | null },
  options: { agent?: boolean } = {},
): OngletFiche[] {
  const onglets: OngletFiche[] = [
    { cle: 'documents', libelle: avecCompteur('Documents', compteurs.documents) },
    { cle: 'signalements', libelle: avecCompteur('Signalements', compteurs.signalements) },
    { cle: 'propositions', libelle: avecCompteur('Propositions', compteurs.propositions) },
    { cle: 'historique', libelle: 'Historique' },
  ]
  if (options.agent) {
    onglets.push({ cle: 'agent', libelle: 'Interroger avec un agent' })
  }
  return onglets
}

export const ONGLET_PAR_DEFAUT: CleOnglet = 'documents'

export type Redirection
  = | { type: 'onglet', cle: CleOnglet }
    | { type: 'ancre', cle: 'consignes' }
    | { type: 'page', vers: string }

/** Les anciennes adresses de la fiche (`?onglet=…`) et où elles mènent désormais. */
export function ongletDepuisAncien (cle: unknown, id: string): Redirection | null {
  const base = `/c/${encodeURIComponent(id)}`
  switch (cle) {
    case 'consulter':
    case 'discussion':
      return { type: 'onglet', cle: 'historique' }
    case 'signaler':
      return { type: 'onglet', cle: 'signalements' }
    case 'proposer':
      return { type: 'onglet', cle: 'propositions' }
    case 'prompt':
      return { type: 'ancre', cle: 'consignes' }
    case 'feedback':
      return { type: 'page', vers: `${base}/qualite?onglet=avis` }
    case 'qr':
    case 'generation':
      return { type: 'page', vers: `${base}/qualite` }
    default:
      return null
  }
}

/**
 * La ligne de métadonnées : catégorie · N documents · créée le … · mise à jour … · responsable.
 *  Un élément inconnu est omis, jamais remplacé par un vide.
 */
export function ligneMeta (
  col: { categorie_libelle?: string | null, nb_documents?: number | null, cree_le?: string | null, mise_a_jour?: string | null, responsable?: string | null },
): string {
  const n = col.nb_documents
  return [
    col.categorie_libelle || '',
    typeof n === 'number' ? `${n} document${n > 1 ? 's' : ''}` : '',
    col.cree_le ? `créée le ${col.cree_le}` : '',
    col.mise_a_jour ? `mise à jour ${col.mise_a_jour}` : '',
    col.responsable || '',
  ].map(s => s.trim()).filter(Boolean).join(' · ')
}

const LONGUEUR_MAX_APERCU = 600
const FINS_DE_LIGNE = /\r\n?/g

/**
 * Les premières lignes des consignes, en texte (jamais interprété comme du HTML), bornées en
 *  nombre de lignes et en longueur. `tronque` dit qu'il en reste.
 */
export function apercuConsignes (texte: string | null | undefined, lignes = 4): { texte: string, tronque: boolean } {
  const toutes = String(texte ?? '').replace(FINS_DE_LIGNE, '\n').trim().split('\n')
  let apercu = toutes.slice(0, lignes).join('\n')
  let tronque = toutes.length > lignes
  if (apercu.length > LONGUEUR_MAX_APERCU) {
    apercu = `${apercu.slice(0, LONGUEUR_MAX_APERCU).trimEnd()}…`
    tronque = true
  }
  return { texte: apercu, tronque }
}

const FUSEAU_EXPLICITE = /(?:Z|[+-]\d{2}:?\d{2})$/

/**
 * Une date du serveur (ISO, UTC, souvent sans fuseau) écrite en français : « 12 mars 2026 »,
 *  ou « 12 mars » sans l'année ; vide si absente ou illisible.
 */
export function dateFiche (iso: string | null | undefined, annee = true): string {
  if (!iso) {
    return ''
  }
  const d = new Date(FUSEAU_EXPLICITE.test(iso) ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) {
    return ''
  }
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: annee ? 'long' : 'short', ...(annee ? { year: 'numeric' } : {}), timeZone: 'Europe/Paris' })
}
