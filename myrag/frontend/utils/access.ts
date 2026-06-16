/**
 * Identification des droits MyRAG à partir des groupes Keycloak.
 *
 * Convention (cf. backend app/services/access.py) :
 *   /myrag/<collection>        → membre (lecture)
 *   /myrag/<collection>-admin  → admin de la collection
 *   /myrag/superadmin          → opérateur global (voit le menu Administration)
 *
 * Le claim `groups` peut arriver avec ou sans slash initial : on normalise.
 */

const ROOT = 'myrag'
const SUPERADMIN = 'superadmin'

function normalise(path: string): string {
  return '/' + String(path).replace(/^\/+|\/+$/g, '')
}

/** Vrai si l'utilisateur est super-admin MyRAG (membre de /myrag/superadmin). */
export function isAdminGroup(groups: string[] | null | undefined): boolean {
  if (!Array.isArray(groups)) return false
  const target = `/${ROOT}/${SUPERADMIN}`
  return groups.some((g) => normalise(g) === target)
}
