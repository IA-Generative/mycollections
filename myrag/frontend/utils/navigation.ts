/**
 * Les entrées du menu principal et des sous-menus : ce que l'en-tête et les fiches affichent,
 * calculé en pur pour être testé. Une entrée sous drapeau n'existe que si le serveur la déclare
 * (capacités) ; drapeaux à faux, le menu est exactement celui d'avant le chantier des assistants.
 *
 * Architecture cible (ADR-0003), appliquée au menu par le lot D : Accueil · Collections ·
 * Assistants · Réseau d'entraide · Catalogue · Guide.
 */
import type { Capacites } from './capacites'

export interface EntreeMenu {
  libelle: string
  vers: string
  /** La page n'est « courante » que sur cette adresse exacte (sinon : tout son sous-arbre). */
  exact?: boolean
}

export function entreesPrincipales (c: Pick<Capacites, 'demandes' | 'assistants' | 'entraide'>, admin: boolean): EntreeMenu[] {
  const entrees: EntreeMenu[] = [{ libelle: 'Accueil', vers: '/', exact: true }]
  if (c.assistants) {
    entrees.push({ libelle: 'Assistants', vers: '/assistants' })
  }
  entrees.push({ libelle: 'Catalogue', vers: '/admin/catalog', exact: true })
  if (c.entraide) {
    entrees.push({ libelle: 'Réseau d\'entraide', vers: '/entraide' })
  }
  else if (c.demandes) {
    entrees.push({ libelle: 'Demandes de la communauté', vers: '/demandes' })
  }
  entrees.push({ libelle: 'Soyez acteurs vous-mêmes', vers: '/guide' })
  if (admin) {
    entrees.push({ libelle: 'Administration', vers: '/admin' })
  }
  return entrees
}

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
