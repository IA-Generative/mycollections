/**
 * Les entrées du menu principal et des sous-menus : ce que l'en-tête et les fiches affichent,
 * calculé en pur pour être testé. Une entrée sous drapeau n'existe que si le serveur la déclare
 * (capacités).
 *
 * Menu décidé par la refonte ergonomique (ADR-0003, amendée le 2026-10-19) : Accueil · Catalogue ·
 * Mes collections[ & assistants] (le volet) · Entraide · [Administration]. « Soyez acteurs
 * vous-mêmes » passe en pied de page (`ENTREES_PIED_DE_PAGE`).
 */
import type { Capacites } from './capacites'

export interface EntreeMenu {
  libelle: string
  vers: string
  /** La page n'est « courante » que sur cette adresse exacte (sinon : tout son sous-arbre). */
  exact?: boolean
  /** Classe d'icône DSFR (`fr-icon-…`) affichée devant le libellé. */
  icone?: string
  /** L'entrée s'ouvre en volet (« Mes collections ») : le gabarit en fournit le contenu. */
  volet?: boolean
}

type CapacitesMenu = Pick<Capacites, 'demandes' | 'assistants' | 'entraide'>

/**
 * « Mes collections & assistants » quand les assistants existent ; sinon « Mes collections » :
 *  rien n'annonce une fonction éteinte.
 */
export function libelleMesCollections (c: Pick<Capacites, 'assistants'>): string {
  return c.assistants ? 'Mes collections & assistants' : 'Mes collections'
}

/**
 * L'entrée Entraide : le réseau d'entraide s'il est allumé, sinon les demandes de la
 *  communauté, sinon rien.
 */
export function entreeEntraide (c: Pick<Capacites, 'demandes' | 'entraide'>): EntreeMenu | null {
  const vers = c.entraide ? '/entraide' : c.demandes ? '/demandes' : null
  return vers ? { libelle: 'Entraide', vers, icone: 'fr-icon-team-line' } : null
}

export function entreesPrincipales (c: CapacitesMenu, admin: boolean): EntreeMenu[] {
  const entrees: EntreeMenu[] = [
    { libelle: 'Accueil', vers: '/', exact: true },
    { libelle: 'Catalogue', vers: '/admin/catalog', exact: true },
    { libelle: libelleMesCollections(c), vers: '/mes-collections', volet: true },
  ]
  const entraide = entreeEntraide(c)
  if (entraide) {
    entrees.push(entraide)
  }
  if (admin) {
    entrees.push({ libelle: 'Administration', vers: '/admin' })
  }
  return entrees
}

/** Les liens du pied de page. */
export const ENTREES_PIED_DE_PAGE: readonly EntreeMenu[] = [
  { libelle: 'Soyez acteurs vous-mêmes', vers: '/guide' },
]

export function estActive (e: EntreeMenu, chemin: string): boolean {
  return e.exact ? chemin === e.vers : chemin.startsWith(e.vers)
}

/** Les rubriques d'un assistant, dans l'ordre de l'architecture cible. */
export const RUBRIQUES_ASSISTANT = [
  { cle: 'sources', libelle: 'Sources' },
  { cle: 'consignes', libelle: 'Consignes' },
  { cle: 'fiables', libelle: 'Réponses fiables' },
  { cle: 'qualite', libelle: 'Qualité' },
  { cle: 'publication', libelle: 'Publication' },
  { cle: 'bac-a-sable', libelle: 'Bac à sable' },
] as const

export function sousMenuAssistant (id: string): EntreeMenu[] {
  const base = `/assistants/${encodeURIComponent(id)}`
  return RUBRIQUES_ASSISTANT.map(r => ({ libelle: r.libelle, vers: `${base}/${r.cle}`, exact: true }))
}

/** Les rubriques d'une collection (architecture cible) ; branchées sur la fiche par le lot D. */
export function sousMenuCollection (id: string): EntreeMenu[] {
  const base = `/c/${encodeURIComponent(id)}`
  return [
    { libelle: 'Vue d\'ensemble', vers: base, exact: true },
    { libelle: 'Documents', vers: `${base}?onglet=documents`, exact: true },
    { libelle: 'Qualité', vers: `${base}/qualite` },
    { libelle: 'Publication', vers: `${base}/publish` },
  ]
}
