/**
 * Helpers de nom de collection partagés par le wizard de création.
 *
 * La disponibilité d'un nom est désormais vérifiée côté serveur (endpoint
 * autoritaire /api/collections/check-name) car la liste vue par le client est
 * filtrée par groupe : un nom déjà pris mais invisible passait « disponible »
 * puis échouait en 409 à la création. Ces helpers couvrent les bouts purs
 * (normalisation de la saisie, détection du conflit 409).
 */

/** Minuscules, sans accents (é → e : on TRANSLITTÈRE, on ne supprime pas — « Sécurité »
 *  donnait `scurit`). */
function sansAccents(s: string): string {
  return (s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
}

/** Normalise la saisie en identifiant : tout ce qui n'est pas [a-z0-9] devient UN tiret. */
export function slugifyCollectionName(s: string): string {
  return sansAccents(s).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

const MOTS_VIDES = new Set(['le', 'la', 'les', 'l', 'un', 'une', 'des', 'de', 'du', 'd', 'et', 'ou', 'a', 'au', 'aux', 'en', 'sur', 'pour', 'par', 'dans'])

/** Les règles servies par GET /api/collections/regles-nommage. */
export interface ReglesNommage {
  min: number
  max: number
  prefixes_bannis: string[]
  reserves: string[]
  motifs: Record<string, string>
}

export const REGLES_PAR_DEFAUT: ReglesNommage = {
  min: 3,
  max: 40,
  prefixes_bannis: ['demo-', 'amorce-', 'rag-', 'test-'],
  reserves: ['all', 'default', 'alias', 'check-name', 'regles-nommage', 'templates'],
  motifs: {
    empty: 'Donnez un identifiant.',
    longueur: 'Entre 3 et 40 caractères.',
    format: 'Minuscules, chiffres et tirets seulement, en commençant par une lettre (ex. codes-natinf).',
    prefixe: "Ce préfixe dit d'où vient la collection, pas ce qu'elle contient : nommez-la par son contenu.",
    reserve: "Ce mot est réservé par l'application.",
  },
}

/** « Droit des étrangers » → `droit-etrangers`. Même règle que app/services/nommage.deriver_identifiant. */
export function deriverIdentifiant(titre: string, max = 40): string {
  const mots = sansAccents(titre).split(/[^a-z0-9]+/).filter(Boolean)
  const utiles = mots.filter(m => !MOTS_VIDES.has(m))
  let ident = (utiles.length ? utiles : mots).join('-').replace(/^[0-9-]+/, '')
  if (ident.length > max) {
    const coupe = ident.slice(0, max + 1)
    ident = coupe.includes('-') ? coupe.slice(0, coupe.lastIndexOf('-')) : ident.slice(0, max)
  }
  return ident.replace(/^-+|-+$/g, '')
}

/** La clé du motif de refus (celles du serveur), ou null si l'identifiant est acceptable. */
export function motifRefus(ident: string, regles: ReglesNommage = REGLES_PAR_DEFAUT): string | null {
  if (!ident) return 'empty'
  if (ident.length < regles.min || ident.length > regles.max) return 'longueur'
  if (!/^[a-z][a-z0-9]*(-[a-z0-9]+)*$/.test(ident)) return 'format'
  if (regles.reserves.includes(ident)) return 'reserve'
  if (regles.prefixes_bannis.some(p => ident.startsWith(p))) return 'prefixe'
  return null
}

/** Vrai si l'erreur d'API correspond à un conflit de nom (HTTP 409). */
export function isConflictError(e: unknown): boolean {
  const msg = (e instanceof Error ? e.message : String(e ?? ''))
  return msg.includes('409') || /already exists/i.test(msg)
}
