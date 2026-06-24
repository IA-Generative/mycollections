/**
 * Helpers de nom de collection partagés par le wizard de création.
 *
 * La disponibilité d'un nom est désormais vérifiée côté serveur (endpoint
 * autoritaire /api/collections/check-name) car la liste vue par le client est
 * filtrée par groupe : un nom déjà pris mais invisible passait « disponible »
 * puis échouait en 409 à la création. Ces helpers couvrent les bouts purs
 * (normalisation de la saisie, détection du conflit 409).
 */

/** Normalise la saisie en identifiant : minuscules, espaces -> tirets, [a-z0-9-]. */
export function slugifyCollectionName(s: string): string {
  return (s || '')
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
}

/** Vrai si l'erreur d'API correspond à un conflit de nom (HTTP 409). */
export function isConflictError(e: unknown): boolean {
  const msg = (e instanceof Error ? e.message : String(e ?? ''))
  return msg.includes('409') || /already exists/i.test(msg)
}
