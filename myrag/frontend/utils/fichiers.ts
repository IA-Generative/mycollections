/**
 * Fichiers à l'écran (docs/fichiers.md) : les instances de Drive qu'on peut importer, leur plafond de
 * sensibilité, et la règle qui en découle — une collection ne descend jamais sous le niveau des
 * documents de son instance ; elle peut monter. Fonctions pures, testées dans
 * tests/unit/fichiers.test.ts. Miroir de `app/services/sensibilite.py`.
 */
import { SENSIBILITES } from './libelles'

export interface InstanceFichiers {
  id: string
  titre: string
  zone: string
  description: string
  hote: string
  sensibilite_max: string
  sensibilite_libelle: string
  niveaux_permis: string[]
}

/** L'échelle, du moins protégé au plus protégé (l'ordre de `SENSIBILITES`). */
export const ECHELLE: readonly string[] = SENSIBILITES.map(s => s.valeur)

export function rang (niveau: string): number {
  const i = ECHELLE.indexOf(niveau)
  return i < 0 ? ECHELLE.length - 1 : i
}

/** Un contenu de ce niveau peut-il entrer sous ce plafond ? */
export function compatible (contenu: string, plafond: string): boolean {
  return rang(contenu) <= rang(plafond)
}

/** Les niveaux qu'une collection peut prendre, son plancher compris, avec leur libellé. */
export function niveauxPermis (plancher: string): { valeur: string, libelle: string }[] {
  return SENSIBILITES.filter(s => rang(s.valeur) >= rang(plancher)).map(s => ({ valeur: s.valeur, libelle: s.libelle }))
}

/** La couleur DSFR du badge de plafond : vert pour public, bleu pour interne, orange puis rouge au-delà. */
export function couleurPlafond (niveau: string): string {
  const r = rang(niveau)
  if (r === 0) {
    return 'fr-badge--success'
  }
  if (r === 1) {
    return 'fr-badge--info'
  }
  return r <= 3 ? 'fr-badge--warning' : 'fr-badge--error'
}

/** « Mes fichiers (bêta) · internet, bêta » — de quoi reconnaître une instance d'un coup d'œil. */
export function libelleInstance (i: Pick<InstanceFichiers, 'titre' | 'zone' | 'hote'>): string {
  return [i.titre, i.zone || i.hote].filter(Boolean).join(' · ')
}

/** Une collection importée de Fichiers (sa page de gestion propose « Mettre à jour »). */
export function estCollectionFichiers (fiche: { source_type?: string | null } | null | undefined): boolean {
  return fiche?.source_type === 'fichiers'
}

/** Une collection importée avec les droits de qui l'importe : Résana ou Fichiers. */
export function sourceImportee (fiche: { source_type?: string | null } | null | undefined): 'resana' | 'fichiers' | null {
  const s = fiche?.source_type
  return s === 'resana' || s === 'fichiers' ? s : null
}

/** La confirmation demandée avant d'ouvrir une collection Fichiers à un groupe. */
export const CONFIRMATION_DROITS_FICHIERS = 'Je confirme que chaque membre de ces groupes a accès, dans Fichiers, aux dossiers indexés. Sinon, il verra les réponses, mais les liens vers les documents cités ne s\'ouvriront pas pour lui.'
