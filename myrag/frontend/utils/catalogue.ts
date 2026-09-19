/**
 * Le catalogue tel qu'on le lit : un TITRE par collection (jamais l'identifiant
 * technique en premier), des collections rangées par rubrique, une recherche qui
 * ne bute pas sur les accents. Fonctions pures — testées dans tests/unit.
 */
import type { Categorie, Collection, GroupeDeCollections } from '~/types/collection'

export const NON_CLASSEES = 'Non classées'

const PREFIXES_DE_PROVENANCE = ['demo-', 'amorce-', 'rag-', 'test-']
const SIGLES = new Set(['ceseda', 'dgef', 'faq', 'sdis', 'baac', 'natinf', 'ssmsi', 'rne', 'sdst', 'anef', 'ta', 'caa', 'cnda', 'cedh', 'rh', 'si', 'pdf', 'md'])

/** Même règle que app/services/nommage.titre_depuis_nom : le dernier recours. */
export function titreDepuisNom(name: string): string {
  let n = (name || '').trim().toLowerCase()
  const p = PREFIXES_DE_PROVENANCE.find(x => n.startsWith(x) && n.length > x.length)
  if (p) n = n.slice(p.length)
  const mots = n.split(/[-_.\s]+/).filter(Boolean)
  if (!mots.length) return name || ''
  return mots
    .map((m, i) => (SIGLES.has(m) ? m.toUpperCase() : i === 0 ? m.charAt(0).toUpperCase() + m.slice(1) : m))
    .join(' ')
}

/** Le titre à montrer : celui de la fiche, sinon déduit de l'identifiant. */
export function titreDe(c: Pick<Collection, 'name' | 'titre'> | null | undefined): string {
  if (!c) return ''
  return (c.titre || '').trim() || titreDepuisNom(c.name)
}

/** Minuscules, sans accents : « Élus » et « elus » se trouvent l'un l'autre. */
export function normaliser(s: unknown): string {
  return String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()
}

/** Tous les mots de la requête doivent se trouver dans le titre, l'identifiant, la
 *  description, le contact ou la source — dans n'importe quel ordre. */
export function filtrerCollections<T extends Collection>(collections: T[], requete: string): T[] {
  const mots = normaliser(requete).split(/\s+/).filter(Boolean)
  if (!mots.length) return collections
  return collections.filter((c) => {
    const foin = normaliser([titreDe(c), c.name, c.description, c.contact_name, c.source_type].join(' '))
    return mots.every(m => foin.includes(m))
  })
}

function parTitre(a: Collection, b: Collection): number {
  return titreDe(a).localeCompare(titreDe(b), 'fr', { sensitivity: 'base' })
}

/**
 * Range les collections par rubrique, dans l'ordre réglé par l'administration.
 * Une rubrique sans collection n'apparaît pas (sauf `garderVides`, pour l'écran
 * d'administration) ; une clé inconnue ou absente tombe dans « Non classées », en dernier.
 */
export function grouperParCategorie(
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
  if (reste.length) rendus.push({ cle: null, libelle: NON_CLASSEES, description: '', collections: reste })
  return rendus
}

/** Une clé de rubrique proposée depuis son libellé : « Droit des étrangers » → droit-des-etrangers. */
export function cleDepuisLibelle(libelle: string): string {
  return normaliser(libelle).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64).replace(/-+$/g, '')
}
