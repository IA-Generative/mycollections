/**
 * Les groupes du claim s'ils sont en CHEMINS COMPLETS (mapper Keycloak `full.path=true`),
 * sinon une liste vide — exactement comme côté serveur (app/services/access.py `chemins`) :
 * un nom court n'est pas unique dans le realm, et n'importe qui en crée un homonyme dans
 * keycloak-comu. Un claim dont une seule valeur n'a pas de « / » initial est en noms courts.
 */
export function groupPaths(groups: unknown): string[] {
  if (!Array.isArray(groups)) return []
  const valeurs = groups.filter((g): g is string => typeof g === 'string')
  if (valeurs.some((g) => !g.startsWith('/'))) return []
  return valeurs
}

/**
 * Les groupes saisis pour un partage, un par ligne (ou séparés par des virgules) : sans espaces
 * autour, sans ligne vide, sans doublon, dans l'ordre de saisie.
 */
export function lignesVersGroupes(texte: string): string[] {
  return [...new Set(texte.split(/[\n,]/).map((g) => g.trim()).filter(Boolean))]
}
