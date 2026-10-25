/**
 * Les capacités du service : ce que le serveur applique (`/api/config`, menu commun et
 * surcharge de l'environnement), avec repli sur `/_beta/capacites.json` (le menu commun, même
 * origine). Un drapeau n'est vrai que s'il vaut exactement `true` — jamais « truthy », comme le
 * fait le menu lui-même.
 */
export const DRAPEAUX = ['demandes', 'signalements', 'assistants', 'entraide', 'resana', 'fichiers'] as const
export type Drapeau = typeof DRAPEAUX[number]

export type Capacites = Record<Drapeau, boolean> & { seuil_chantier: number }

export const CAPACITES_DEFAUT: Capacites = {
  demandes: false,
  signalements: false,
  assistants: false,
  entraide: false,
  resana: false,
  fichiers: false,
  seuil_chantier: 5,
}

export function normaliserCapacites (brut: unknown, repli: Capacites = CAPACITES_DEFAUT): Capacites {
  const c = { ...repli }
  if (!brut || typeof brut !== 'object') {
    return c
  }
  const b = brut as Record<string, unknown>
  for (const nom of DRAPEAUX) {
    c[nom] = b[nom] === true
  }
  const s = b.seuil_chantier
  if (typeof s === 'number' && Number.isInteger(s) && s >= 1 && s <= 1000) {
    c.seuil_chantier = s
  }
  return c
}
