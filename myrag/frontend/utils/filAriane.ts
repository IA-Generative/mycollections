/**
 * Le fil d'Ariane des pages d'une collection : Accueil › Catalogue › {collection} › {rubrique}.
 *
 * « Catalogue » mène au catalogue (`/admin/catalog`, le lien « Catalogue » de la navigation),
 * pas à l'accueil : c'est de là que l'on vient quand on ouvre une collection.
 */

export interface MaillonFil {
  libelle: string
  /** Absent sur le dernier maillon : c'est la page où l'on est. */
  vers?: string
}

export function maillonsFil(collection: string, titre: string, rubrique?: string): MaillonFil[] {
  const fiche = `/c/${collection}`
  const maillons: MaillonFil[] = [
    { libelle: 'Accueil', vers: '/' },
    { libelle: 'Catalogue', vers: '/admin/catalog' },
    { libelle: titre || collection, vers: fiche },
  ]
  if (rubrique) maillons.push({ libelle: rubrique })
  else delete maillons[maillons.length - 1].vers
  return maillons
}

/**
 * L'onglet de la fiche que porte l'adresse (`?onglet=documents`). Une valeur absente,
 * inconnue ou répétée rend l'onglet par défaut : un lien ancien ou abîmé ouvre la fiche,
 * jamais une page vide.
 */
export function ongletDeLAdresse(valeur: unknown, connus: string[], parDefaut: string): string {
  const v = Array.isArray(valeur) ? valeur[0] : valeur
  return typeof v === 'string' && connus.includes(v) ? v : parDefaut
}

/** Le libellé d'un onglet sans son compteur (« Avis (3) » → « Avis ») : le fil ne bouge pas à chaque avis. */
export function libelleSansCompteur(libelle: string): string {
  return libelle.replace(/\s*\(\d+\)$/, '')
}
