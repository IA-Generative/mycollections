/**
 * Les capacités du service, lues dans `/_beta/capacites.json` (même origine, servi
 * par le menu commun) avec repli sur `/api/config`. Un drapeau n'est vrai que s'il
 * vaut exactement `true` — jamais « truthy », comme le fait le menu lui-même.
 */
export interface Capacites {
  demandes: boolean
  signalements: boolean
  seuil_chantier: number
}

export const CAPACITES_DEFAUT: Capacites = { demandes: false, signalements: false, seuil_chantier: 5 }

export function normaliserCapacites(brut: unknown, repli: Capacites = CAPACITES_DEFAUT): Capacites {
  const c = { ...repli }
  if (!brut || typeof brut !== 'object') return c
  const b = brut as Record<string, unknown>
  c.demandes = b.demandes === true
  c.signalements = b.signalements === true
  const s = b.seuil_chantier
  if (typeof s === 'number' && Number.isInteger(s) && s >= 1 && s <= 1000) c.seuil_chantier = s
  return c
}
