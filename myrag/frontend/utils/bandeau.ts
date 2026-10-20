/**
 * Le bandeau d'information de l'accueil : un message éditorial que chacun peut fermer. Fermé, il
 * ne revient pas tant que son identifiant ne change pas : changer `id` republie un message.
 * `BANDEAU` à null : pas de bandeau.
 */
export interface Bandeau {
  /** Change à chaque nouveau message. */
  id: string
  titre: string
  texte: string
  lien?: { libelle: string, vers: string }
}

export const BANDEAU: Bandeau | null = {
  id: '2026-10-refonte',
  titre: 'Mes collections fait peau neuve.',
  texte: 'Un catalogue plus lisible, une fiche par collection, et une création guidée en cinq étapes.',
  lien: { libelle: 'Découvrir le guide', vers: '/guide' },
}

export const CLE_BANDEAUX_FERMES = 'mycollections.bandeaux-fermes'

/** Le bandeau s'affiche s'il existe et que la personne ne l'a pas déjà fermé. */
export function bandeauAffiche (b: Bandeau | null, fermes: readonly string[]): boolean {
  return !!b && !fermes.includes(b.id)
}

/** Lit la liste des bandeaux fermés ; une valeur illisible vaut « aucun ». */
export function lireFermes (brut: string | null): string[] {
  try {
    const v = JSON.parse(brut || '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  }
  catch {
    return []
  }
}
