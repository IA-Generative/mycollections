/**
 * Ce que l'accueil raconte — fonctions pures, testées dans tests/unit.
 * Quatre tuiles (refonte du 2026-10-19) : Découvrir · Explorer le catalogue · Gérer mes
 * collections · Créer une nouvelle collection. Il ne reproche rien à qui ne gère rien.
 */
import type { Capacites } from './capacites'
import type { Categorie, Collection } from '~/types/collection'

export interface Indicateurs { collections: number, categories: number, documents: number }

/** Les trois chiffres de la tuile « Découvrir », sur ce que la personne peut réellement lire. */
export function indicateurs (collections: Collection[], categories: Categorie[]): Indicateurs {
  const lisibles = collections.filter(c => !c.orphan)
  const connues = new Set(categories.map(c => c.cle))
  return {
    collections: lisibles.length,
    categories: new Set(lisibles.map(c => c.categorie).filter((k): k is string => !!k && connues.has(k))).size,
    documents: lisibles.reduce((n, c) => n + (Number(c.file_count) || 0), 0),
  }
}

const MILLIERS = /\B(?=(\d{3})+(?!\d))/g

/** 31400 → « 31 400 » (espace fine insécable, comme on l'écrit en français). */
export function nombre (n: number): string {
  return String(Math.round(n || 0)).replace(MILLIERS, ' ')
}

export interface Porte { cle: string, libelle: string, nb: number }

/** La clé de filtre du catalogue pour les collections sans catégorie connue. */
export const CLE_NON_CLASSEES = '__aucune__'

/** Les portes d'entrée du catalogue : les catégories non vides, dans l'ordre de l'administration. */
export function portes (collections: Collection[], categories: Categorie[]): Porte[] {
  return [...categories]
    .sort((a, b) => a.ordre - b.ordre)
    .map(k => ({ cle: k.cle, libelle: k.libelle, nb: collections.filter(c => !c.orphan && c.categorie === k.cle).length }))
    .filter(p => p.nb > 0)
}

export interface BilanPartage {
  collections: { name: string, titre: string, questions: number, publiee: boolean, signalements_ouverts: number }[]
  actives: number
  questions: number
  personnes: number | null
  signalements_ouverts?: number
  /** Mes propres questions sur la fenêtre : elles ne comptent pas, mais on les dit. */
  mes_essais?: number
  fenetre_jours: number
}

/**
 * La porte « Non classées » : les collections sans catégorie, ou d'une catégorie disparue.
 *  Rien s'il n'y en a pas.
 */
export function porteNonClassees (collections: Collection[], categories: Categorie[]): Porte | null {
  const connues = new Set(categories.map(c => c.cle))
  const nb = collections.filter(c => !c.orphan && (!c.categorie || !connues.has(c.categorie))).length
  return nb ? { cle: CLE_NON_CLASSEES, libelle: 'Non classées', nb } : null
}

export interface Kpi { valeur: number, libelle: string, alerte?: boolean }

function pluriel (n: number, singulier: string, plurielle = `${singulier}s`): string {
  return n > 1 ? plurielle : singulier
}

/**
 * Les chiffres de la tuile « Gérer mes collections » : collections actives, questions de collègues
 * sur la fenêtre, collègues aidés (seulement au-dessus du seuil, quand le serveur donne un nombre),
 * signalements à traiter (seulement s'il y en a). Rien pour qui ne gère rien.
 */
export function indicateursDeGestion (b: BilanPartage | null): Kpi[] {
  if (!b || !b.collections.length) {
    return []
  }
  const kpis: Kpi[] = [
    { valeur: b.actives, libelle: pluriel(b.actives, 'collection active', 'collections actives') },
    { valeur: b.questions, libelle: `${pluriel(b.questions, 'question')} de collègues en ${b.fenetre_jours} jours` },
  ]
  if (b.personnes) {
    kpis.push({ valeur: b.personnes, libelle: pluriel(b.personnes, 'collègue aidé', 'collègues aidés') })
  }
  const signalements = b.signalements_ouverts || 0
  if (signalements > 0) {
    kpis.push({ valeur: signalements, libelle: `${pluriel(signalements, 'signalement')} à traiter`, alerte: true })
  }
  return kpis
}

export interface Exemple { name: string, titre: string, categorie_libelle?: string | null, question: string, autres?: boolean }

export interface Tuile {
  cle: 'decouvrir' | 'explorer' | 'gerer' | 'creer'
  titre: string
  description: string
  /** Le lien principal de la tuile (adresse et, s'il y a lieu, paramètres). */
  vers: string | { path: string, query: Record<string, string> }
  action: string
  icone: string
  kpis: Kpi[]
  mention?: string
}

/**
 * Les quatre tuiles de l'accueil, dans l'ordre décidé. « & assistants » ne s'affiche que si le
 *  drapeau `assistants` est vrai.
 */
export function tuilesAccueil (
  capacites: Pick<Capacites, 'assistants'>,
  bilan: BilanPartage | null,
  exemple: Exemple | null,
  chiffres: Indicateurs | null,
): Tuile[] {
  const assistants = capacites.assistants === true
  const nb = chiffres?.collections ?? null
  return [
    {
      cle: 'decouvrir',
      titre: 'Découvrir',
      description: 'Posez une question à une collection prête à l\'emploi, pour voir ce que ça donne.',
      vers: exemple ? { path: `/c/${exemple.name}/playground`, query: { q: exemple.question } } : '/admin/catalog',
      action: exemple ? 'Essayer cette question' : 'Voir le catalogue',
      icone: 'fr-icon-search-line',
      kpis: [],
    },
    {
      cle: 'explorer',
      titre: 'Explorer le catalogue',
      description: 'Toutes les collections, rangées par catégorie, avec leur fraîcheur et l\'avis des usagers.',
      vers: '/admin/catalog',
      action: 'Voir le catalogue',
      icone: 'fr-icon-folder-2-line',
      kpis: nb === null ? [] : [{ valeur: nb, libelle: `${pluriel(nb, 'collection')} à interroger` }],
    },
    {
      cle: 'gerer',
      titre: assistants ? 'Gérer mes collections & assistants' : 'Gérer mes collections',
      description: 'Suivre ce qu\'en pensent vos collègues et piloter la qualité.',
      vers: '/mes-collections',
      action: assistants ? 'Ouvrir mes collections & assistants' : 'Ouvrir mes collections',
      icone: 'fr-icon-checkbox-circle-line',
      kpis: indicateursDeGestion(bilan),
    },
    {
      cle: 'creer',
      titre: assistants ? 'Créer une nouvelle collection & assistant' : 'Créer une nouvelle collection',
      description: 'Un assistant en 5 étapes : d\'où viennent vos documents, comment les nommer, les déposer, vérifier les réponses, partager.',
      vers: '/admin/create',
      action: 'Commencer',
      icone: 'fr-icon-add-circle-line',
      kpis: [],
      mention: 'Aucune compétence technique requise.',
    },
  ]
}
