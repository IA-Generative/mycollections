/**
 * La liste déroulante riche (sélection avec recherche) : maquette DSFR « Liste déroulante riche »
 * (bêta, pas encore en code) et motif « combobox » du W3C (ARIA APG). Fonctions pures, testées
 * dans tests/unit/listeRiche.test.ts ; le composant est components/ListeDeroulanteRiche.vue.
 */

export interface OptionRiche {
  value: string
  label: string
  /** Une précision affichée en gris sous le libellé (et cherchée aussi). */
  hint?: string
}

const ESPACES = /\s+/
const DIACRITIQUES = /[\u0300-\u036F]/g

function normaliser (s: string): string {
  return s.normalize('NFD').replace(DIACRITIQUES, '').toLowerCase()
}

/** Les options dont le libellé ou la précision contient chaque mot tapé (accents et casse ignorés). */
export function filtrerOptions (options: readonly OptionRiche[], recherche: string): OptionRiche[] {
  const mots = normaliser(recherche).split(ESPACES).filter(Boolean)
  if (!mots.length) {
    return [...options]
  }
  return options.filter((o) => {
    const texte = normaliser(`${o.label} ${o.hint || ''}`)
    return mots.every(m => texte.includes(m))
  })
}

/** L'option active après une flèche : on boucle d'un bout à l'autre ; -1 = aucune. */
export function indexSuivant (actuel: number, nombre: number, pas: 1 | -1): number {
  if (nombre <= 0) {
    return -1
  }
  if (actuel < 0) {
    return pas === 1 ? 0 : nombre - 1
  }
  return (actuel + pas + nombre) % nombre
}

/** Ce que l'on annonce aux lecteurs d'écran après une frappe. */
export function annonceResultats (nombre: number): string {
  if (!nombre) {
    return 'Aucun résultat.'
  }
  return `${nombre} résultat${nombre > 1 ? 's' : ''}, flèches haut et bas pour parcourir.`
}
