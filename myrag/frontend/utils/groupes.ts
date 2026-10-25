/**
 * Les groupes du claim s'ils sont en CHEMINS COMPLETS (mapper Keycloak `full.path=true`),
 * sinon une liste vide — exactement comme côté serveur (app/services/access.py `chemins`) :
 * un nom court n'est pas unique dans le realm, et n'importe qui en crée un homonyme dans
 * keycloak-comu. Un claim dont une seule valeur n'a pas de « / » initial est en noms courts.
 */
export function groupPaths (groups: unknown): string[] {
  if (!Array.isArray(groups)) { return [] }
  const valeurs = groups.filter((g): g is string => typeof g === 'string')
  if (valeurs.some(g => !g.startsWith('/'))) { return [] }
  return valeurs
}

/**
 * Les groupes saisis pour un partage, un par ligne (ou séparés par des virgules) : sans espaces
 * autour, sans ligne vide, sans doublon, dans l'ordre de saisie.
 */
export function lignesVersGroupes (texte: string): string[] {
  return [...new Set(texte.split(/[\n,]/).map(g => g.trim()).filter(Boolean))]
}

/** Un groupe proposé au partage : le chemin complet en valeur, le dernier segment en libellé. */
export interface OptionGroupe { value: string, label: string, hint: string }

/** Les groupes de la personne, prêts pour des cases à cocher ; vide si le claim est en noms courts. */
export function optionsGroupes (groups: unknown): OptionGroupe[] {
  return groupPaths(groups).map(g => ({ value: g, label: g.split('/').pop() || g, hint: g }))
}

/** Les groupes retenus : cochés puis saisis à la main, sans doublon (casse ignorée), ordre stable. */
export function fusionnerGroupes (coches: readonly string[], libres: readonly string[]): string[] {
  const vus = new Set<string>()
  const rendu: string[] = []
  for (const g of [...coches, ...libres]) {
    const t = g.trim()
    const cle = t.toLowerCase()
    if (!t || vus.has(cle)) { continue }
    vus.add(cle)
    rendu.push(t)
  }
  return rendu
}
