/**
 * Les entrées du menu principal et des sous-menus : ce que l'en-tête et les fiches affichent,
 * calculé en pur pour être testé. Une entrée sous drapeau n'existe que si le serveur la déclare
 * (capacités).
 *
 * Menu (ADR-0003, amendée le 2026-10-20) : Accueil · Catalogue · Mes collections (avec sa pastille) ·
 * [Assistants] · Entraide · [Administration]. Une collection et un assistant sont deux objets
 * distincts : chacun a son entrée. « Soyez acteurs vous-mêmes » est en pied de page
 * (`ENTREES_PIED_DE_PAGE`).
 */
import type { Capacites } from './capacites'

export interface EntreeMenu {
  libelle: string
  vers: string
  /** La page n'est « courante » que sur cette adresse exacte (sinon : tout son sous-arbre). */
  exact?: boolean
  /** Classe d'icône DSFR (`fr-icon-…`) affichée devant le libellé. */
  icone?: string
  /** L'entrée porte une pastille : le nombre de collections que je gère, fourni par le gabarit. */
  pastille?: boolean
}

type CapacitesMenu = Pick<Capacites, 'demandes' | 'assistants' | 'entraide'>

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
    { libelle: 'Mes collections', vers: '/mes-collections', pastille: true },
  ]
  if (c.assistants) {
    entrees.push({ libelle: 'Assistants', vers: '/assistants' })
  }
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
