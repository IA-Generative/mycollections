/**
 * Identification des droits MyRAG à partir des groupes Keycloak.
 *
 * Convention (cf. backend app/services/access.py) :
 *   /myrag/<collection>        → membre (lecture)
 *   /myrag/<collection>-admin  → admin de la collection
 *   /myrag/superadmin          → opérateur global (voit le menu Administration)
 *
 * Seuls des CHEMINS COMPLETS (mapper Keycloak `full.path=true`) donnent des droits,
 * exactement comme côté backend : un nom court n'est pas unique dans le realm, et
 * n'importe qui peut en créer un homonyme dans keycloak-comu — y compris un nom qui
 * ressemble à un chemin (`myrag/superadmin`). Un claim dont une seule valeur n'a pas
 * de « / » initial est en noms courts : on n'en tire rien.
 */

const ROOT = 'myrag'
const SUPERADMIN = 'superadmin'

/** Les groupes du claim s'ils sont en chemins complets, sinon une liste vide. */
export function groupPaths(groups: unknown): string[] {
  if (!Array.isArray(groups)) return []
  const valeurs = groups.filter((g): g is string => typeof g === 'string')
  if (valeurs.some((g) => !g.startsWith('/'))) return []
  return valeurs
}

/** Vrai si l'utilisateur est super-admin MyRAG (membre de /myrag/superadmin). */
export function isAdminGroup(groups: string[] | null | undefined): boolean {
  const target = `/${ROOT}/${SUPERADMIN}`
  return groupPaths(groups).some((g) => g.replace(/\/+$/, '') === target)
}
