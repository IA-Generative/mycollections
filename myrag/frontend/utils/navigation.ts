/**
 * Les entrées du menu principal : ce que l'en-tête affiche, calculé en pur pour être testé.
 * L'ordre, les libellés, les cibles et la règle « page courante » sont ceux de l'en-tête
 * depuis toujours ; une entrée sous drapeau n'existe que si le menu commun la déclare.
 */
import type { Capacites } from './capacites'

export interface EntreeMenu {
  libelle: string
  vers: string
  /** La page n'est « courante » que sur cette adresse exacte (sinon : tout son sous-arbre). */
  exact?: boolean
}

export function entreesPrincipales (c: Pick<Capacites, 'demandes'>, admin: boolean): EntreeMenu[] {
  const entrees: EntreeMenu[] = [
    { libelle: 'Accueil', vers: '/', exact: true },
    { libelle: 'Catalogue', vers: '/admin/catalog', exact: true },
  ]
  if (c.demandes) {
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
