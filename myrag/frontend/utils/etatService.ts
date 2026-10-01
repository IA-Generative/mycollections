/**
 * L'état du service vu par l'usager : une sonde par composant (Mes collections, et la
 * recherche dans les documents), qui ne se déclare en panne qu'après plusieurs mesures
 * ratées DE SUITE — un hoquet réseau ne doit pas faire clignoter un bandeau. Logique
 * pure, sans Vue ni réseau : le composable `useEtatService` la nourrit.
 */

export type Etat = 'inconnu' | 'ok' | 'ko'

export interface Sonde {
  etat: Etat
  /** Mesures ratées consécutives. */
  echecs: number
  /** Premier échec de la série en cours (ms) — « indisponible depuis ». */
  premierEchec: number | null
  /** Dernier retour à la normale après une panne déclarée (ms). */
  retablieA: number | null
}

/** Deux mesures ratées de suite (≈ 1 min à une mesure toutes les 30 s). */
export const SEUIL_ECHECS = 2

export function sondeInitiale(): Sonde {
  return { etat: 'inconnu', echecs: 0, premierEchec: null, retablieA: null }
}

export function noterMesure(s: Sonde, reussie: boolean, maintenant: number): Sonde {
  if (reussie) {
    return {
      etat: 'ok',
      echecs: 0,
      premierEchec: null,
      retablieA: s.etat === 'ko' ? maintenant : s.retablieA,
    }
  }
  const echecs = s.echecs + 1
  return {
    etat: echecs >= SEUIL_ECHECS ? 'ko' : s.etat,
    echecs,
    premierEchec: s.premierEchec ?? maintenant,
    retablieA: s.retablieA,
  }
}

/** « 14 h 02 » — l'heure telle qu'on la lit dans un message. */
export function heureLisible(ms: number): string {
  const d = new Date(ms)
  return `${d.getHours()} h ${String(d.getMinutes()).padStart(2, '0')}`
}
