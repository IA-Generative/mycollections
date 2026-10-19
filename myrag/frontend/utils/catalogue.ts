/**
 * Le catalogue tel qu'on le lit : un TITRE par collection (jamais l'identifiant
 * technique en premier), des collections rangées par rubrique, une recherche qui
 * ne bute pas sur les accents. Fonctions pures — testées dans tests/unit.
 */
import type { AvisCollection, Categorie, Collection, GroupeDeCollections } from '~/types/collection'

export const NON_CLASSEES = 'Non classées'

const PREFIXES_DE_PROVENANCE = ['demo-', 'amorce-', 'rag-', 'test-']
const SIGLES = new Set(['ceseda', 'dgef', 'faq', 'sdis', 'baac', 'natinf', 'ssmsi', 'rne', 'sdst', 'anef', 'ta', 'caa', 'cnda', 'cedh', 'rh', 'si', 'pdf', 'md'])

const SEPARATEURS_DE_NOM = /[-_.\s]+/
const DIACRITIQUES = /[\u0300-\u036F]/g
const ESPACES = /\s+/
const HORS_CLE = /[^a-z0-9]+/g
const TIRETS_AUX_BORDS = /^-+|-+$/g
const TIRETS_FINAUX = /-+$/

/** Même règle que app/services/nommage.titre_depuis_nom : le dernier recours. */
export function titreDepuisNom (name: string): string {
  let n = (name || '').trim().toLowerCase()
  const p = PREFIXES_DE_PROVENANCE.find(x => n.startsWith(x) && n.length > x.length)
  if (p) {
    n = n.slice(p.length)
  }
  const mots = n.split(SEPARATEURS_DE_NOM).filter(Boolean)
  if (!mots.length) {
    return name || ''
  }
  return mots
    .map((m, i) => (SIGLES.has(m) ? m.toUpperCase() : i === 0 ? m.charAt(0).toUpperCase() + m.slice(1) : m))
    .join(' ')
}

/** Le titre à montrer : celui de la fiche, sinon déduit de l'identifiant. */
export function titreDe (c: Pick<Collection, 'name' | 'titre'> | null | undefined): string {
  if (!c) {
    return ''
  }
  return (c.titre || '').trim() || titreDepuisNom(c.name)
}

/** Minuscules, sans accents : « Élus » et « elus » se trouvent l'un l'autre. */
export function normaliser (s: unknown): string {
  return String(s ?? '').normalize('NFD').replace(DIACRITIQUES, '').toLowerCase().trim()
}

/**
 * Tous les mots de la requête doivent se trouver dans le titre, l'identifiant, la
 *  description, le contact ou la source — dans n'importe quel ordre.
 */
export function filtrerCollections<T extends Collection> (collections: T[], requete: string): T[] {
  const mots = normaliser(requete).split(ESPACES).filter(Boolean)
  if (!mots.length) {
    return collections
  }
  return collections.filter((c) => {
    const foin = normaliser([titreDe(c), c.name, c.description, c.contact_name, c.source_type].join(' '))
    return mots.every(m => foin.includes(m))
  })
}

function parTitre (a: Collection, b: Collection): number {
  return titreDe(a).localeCompare(titreDe(b), 'fr', { sensitivity: 'base' })
}

/**
 * Range les collections par rubrique, dans l'ordre réglé par l'administration.
 * Une rubrique sans collection n'apparaît pas (sauf `garderVides`, pour l'écran
 * d'administration) ; une clé inconnue ou absente tombe dans « Non classées », en dernier.
 */
export function grouperParCategorie (
  collections: Collection[],
  categories: Categorie[],
  garderVides = false,
): GroupeDeCollections[] {
  const rubriques = [...categories].sort((a, b) => a.ordre - b.ordre || a.libelle.localeCompare(b.libelle, 'fr'))
  const connues = new Set(rubriques.map(r => r.cle))
  const groupes: GroupeDeCollections[] = rubriques.map(r => ({
    cle: r.cle,
    libelle: r.libelle,
    description: r.description || '',
    collections: collections.filter(c => c.categorie === r.cle).sort(parTitre),
  }))
  const reste = collections.filter(c => !c.categorie || !connues.has(c.categorie)).sort(parTitre)
  const rendus = garderVides ? groupes : groupes.filter(g => g.collections.length)
  if (reste.length) {
    rendus.push({ cle: null, libelle: NON_CLASSEES, description: '', collections: reste })
  }
  return rendus
}

/** Une clé de rubrique proposée depuis son libellé : « Droit des étrangers » → droit-des-etrangers. */
export function cleDepuisLibelle (libelle: string): string {
  return normaliser(libelle).replace(HORS_CLE, '-').replace(TIRETS_AUX_BORDS, '').slice(0, 64).replace(TIRETS_FINAUX, '')
}

/** Les colonnes du tableau du catalogue, dans l'ordre de la maquette du 2026-10-19. */
export const COLONNES_CATALOGUE = ['Collection', 'État', 'Créée le', 'Mise à jour', 'Avis des usagers', 'Responsable'] as const

const JOUR_MS = 86_400_000
const FUSEAU_EXPLICITE = /(?:Z|[+-]\d{2}:?\d{2})$/

/** Une date du serveur (ISO, en UTC, souvent sans fuseau) ; null si absente ou illisible. */
export function lireDate (iso: string | null | undefined): Date | null {
  if (!iso) {
    return null
  }
  const d = new Date(FUSEAU_EXPLICITE.test(iso) ? iso : `${iso}Z`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** « 12 mars 2026 ». */
export function dateCourte (d: Date | null): string {
  return d ? d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/Paris' }) : '—'
}

/**
 * Depuis quand : « aujourd'hui », « hier », « il y a N jours » (moins d'une semaine),
 *  « il y a N semaines » (jusqu'à 30 jours), « il y a N mois » au-delà.
 */
export function ilYa (date: Date, maintenant: Date): string {
  const jours = Math.max(0, Math.floor((maintenant.getTime() - date.getTime()) / JOUR_MS))
  if (jours === 0) {
    return 'aujourd\'hui'
  }
  if (jours === 1) {
    return 'hier'
  }
  if (jours < 7) {
    return `il y a ${jours} jours`
  }
  if (jours <= 30) {
    const semaines = Math.floor(jours / 7)
    return `il y a ${semaines} semaine${semaines > 1 ? 's' : ''}`
  }
  return `il y a ${Math.max(1, Math.floor(jours / 30))} mois`
}

export interface LibelleAvis {
  /** « 92 % », ou null sans avis. */
  taux: string | null
  /** « 84 avis », ou « Pas encore d'avis ». */
  detail: string
}

/** L'avis des usagers tel qu'on le lit : un taux arrondi et un nombre d'avis. */
export function libelleAvis (avis: AvisCollection | null | undefined): LibelleAvis {
  if (!avis || !avis.total || avis.satisfaction_rate === null || avis.satisfaction_rate === undefined) {
    return { taux: null, detail: 'Pas encore d\'avis' }
  }
  return { taux: `${Math.round(avis.satisfaction_rate * 100)} %`, detail: `${avis.total} avis` }
}

export interface EtatCatalogue { libelle: string, classe: string }

/** Le badge d'état : archivée, sinon l'état de partage. */
export function etatCatalogue (c: Pick<Collection, 'archived_at' | 'publication'>): EtatCatalogue {
  if (c.archived_at) {
    return { libelle: 'Archivée', classe: 'fr-badge--warning' }
  }
  const etats: Record<string, EtatCatalogue> = {
    published: { libelle: 'Publiée', classe: 'fr-badge--success' },
    disabled: { libelle: 'Désactivée', classe: 'fr-badge--warning' },
    archived: { libelle: 'Archivée', classe: 'fr-badge--warning' },
  }
  return etats[c.publication?.state || ''] || { libelle: 'Brouillon', classe: 'fr-badge--info' }
}

export interface LigneCatalogue {
  name: string
  titre: string
  description: string
  etat: EtatCatalogue
  creeeLe: string
  miseAJour: { date: string, ilYa: string | null }
  avis: LibelleAvis
  responsable: { nom: string, courriel: string }
}

/** Ce qu'affiche une ligne du catalogue (texte seulement, jamais du HTML). */
export function ligneCatalogue (c: Collection, maintenant: Date): LigneCatalogue {
  const maj = lireDate(c.derniere_mise_a_jour || c.updated_at)
  return {
    name: c.name,
    titre: titreDe(c),
    description: c.description || '',
    etat: etatCatalogue(c),
    creeeLe: dateCourte(lireDate(c.created_at)),
    miseAJour: { date: dateCourte(maj), ilYa: maj ? ilYa(maj, maintenant) : null },
    avis: libelleAvis(c.avis),
    responsable: { nom: c.contact_name || '', courriel: c.contact_email || '' },
  }
}

export type CleTri = 'recente' | 'satisfaction' | 'titre'

export const TRIS: readonly { cle: CleTri, libelle: string }[] = [
  { cle: 'recente', libelle: 'Mise à jour récente' },
  { cle: 'satisfaction', libelle: 'Satisfaction' },
  { cle: 'titre', libelle: 'Titre' },
]

function horodatage (c: Collection): number | null {
  return lireDate(c.derniere_mise_a_jour || c.updated_at)?.getTime() ?? null
}

function satisfaction (c: Collection): number | null {
  return c.avis && c.avis.total ? c.avis.satisfaction_rate ?? null : null
}

/** Compare deux valeurs, la plus grande d'abord, les absentes (null) en dernier. */
function decroissantNullDernier (a: number | null, b: number | null): number {
  if (a === null || b === null) {
    return a === b ? 0 : a === null ? 1 : -1
  }
  return b - a
}

/** Trie sans muter, de façon stable : à égalité, l'ordre d'entrée est gardé. */
export function trierCollections<T extends Collection> (collections: T[], cle: CleTri): T[] {
  const comparer: (a: T, b: T) => number = cle === 'titre'
    ? (a, b) => titreDe(a).localeCompare(titreDe(b), 'fr', { sensitivity: 'base' })
    : cle === 'satisfaction'
      ? (a, b) => decroissantNullDernier(satisfaction(a), satisfaction(b))
      : (a, b) => decroissantNullDernier(horodatage(a), horodatage(b))
  return collections
    .map((c, i) => ({ c, i }))
    .sort((x, y) => comparer(x.c, y.c) || x.i - y.i)
    .map(x => x.c)
}
