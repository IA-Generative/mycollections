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
 * Les quatre tuiles de l'accueil, dans l'ordre décidé, en version compacte : un titre, une phrase.
 * Les chiffres de celui qui partage ne sont plus dans une tuile : ils ont leur bandeau (`impactDuPartage`).
 * « & assistants » ne s'affiche que si le drapeau `assistants` est vrai.
 */
export function tuilesAccueil (
  capacites: Pick<Capacites, 'assistants'>,
  exemple: Exemple | null,
  chiffres: Indicateurs | null,
): Tuile[] {
  const assistants = capacites.assistants === true
  const nb = chiffres?.collections ?? null
  return [
    {
      cle: 'decouvrir',
      titre: 'Découvrir',
      description: exemple ? `« ${exemple.question} »` : 'Posez une question à une collection partagée.',
      vers: exemple ? { path: `/c/${exemple.name}/playground`, query: { q: exemple.question } } : '/admin/catalog',
      action: exemple ? 'Essayer cette question' : 'Voir le catalogue',
      icone: 'fr-icon-search-line',
      kpis: [],
    },
    {
      cle: 'explorer',
      titre: 'Explorer le catalogue',
      description: nb === null
        ? 'Leur fraîcheur et l\'avis des usagers.'
        : `${nombre(nb)} ${pluriel(nb, 'collection')}, leur fraîcheur, l'avis des usagers.`,
      vers: '/admin/catalog',
      action: 'Voir le catalogue',
      icone: 'fr-icon-folder-2-line',
      kpis: [],
    },
    {
      cle: 'gerer',
      titre: assistants ? 'Suivre mes collections & assistants' : 'Suivre mes collections',
      description: 'Usage, avis des collègues et qualité.',
      vers: '/mes-collections',
      action: 'Ouvrir',
      icone: 'fr-icon-line-chart-line',
      kpis: [],
    },
    {
      cle: 'creer',
      titre: assistants ? 'Partager une nouvelle collection & assistant' : 'Partager une nouvelle collection',
      description: 'En 5 étapes, sans compétence technique.',
      vers: '/admin/create',
      action: 'Commencer',
      icone: 'fr-icon-add-circle-line',
      kpis: [],
    },
  ]
}

export interface Impact {
  fenetre_jours: number
  actives: number
  questions: number
  /** Personnes distinctes aidées ; null sous le seuil (le serveur ne dit pas combien). */
  personnes: number | null
  /** Part des avis positifs sur mes collections, en pourcentage arrondi ; null sans avis. */
  satisfaction: number | null
  avis: number
  signalements: number
  /** La collection la plus interrogée par les collègues, s'il y en a une. */
  plusUtile: { name: string, titre: string, questions: number } | null
}

/**
 * Ce que mes collections ont rendu possible : le bilan d'usage du serveur, et la note que leur
 * donnent les usagers (moyenne pondérée par le nombre d'avis). Rien pour qui ne gère rien.
 */
export function impactDuPartage (
  bilan: BilanPartage | null,
  collections: Pick<Collection, 'name' | 'avis'>[],
): Impact | null {
  if (!bilan || !bilan.collections.length) {
    return null
  }
  const miennes = new Set(bilan.collections.map(c => c.name))
  let avis = 0
  let positifs = 0
  for (const c of collections) {
    if (miennes.has(c.name) && c.avis?.total && c.avis.satisfaction_rate !== null && c.avis.satisfaction_rate !== undefined) {
      avis += c.avis.total
      positifs += c.avis.satisfaction_rate * c.avis.total
    }
  }
  const tete = [...bilan.collections].sort((a, b) => b.questions - a.questions)[0]
  return {
    fenetre_jours: bilan.fenetre_jours,
    actives: bilan.actives,
    questions: bilan.questions,
    personnes: bilan.personnes,
    satisfaction: avis ? Math.round((positifs / avis) * 100) : null,
    avis,
    signalements: bilan.signalements_ouverts || 0,
    plusUtile: tete && tete.questions > 0 ? { name: tete.name, titre: tete.titre, questions: tete.questions } : null,
  }
}

/** La phrase qui donne envie de continuer : jamais un reproche, toujours un pas suivant. */
export function messageImpact (i: Impact): { titre: string, texte: string } {
  if (i.personnes) {
    return {
      titre: `Vous avez aidé ${nombre(i.personnes)} ${pluriel(i.personnes, 'collègue')} en ${i.fenetre_jours} jours.`,
      texte: 'Merci : vos collections leur ont répondu sans qu\'ils aient à vous déranger.',
    }
  }
  if (i.questions > 0) {
    return {
      titre: `Vos collections ont répondu à ${nombre(i.questions)} ${pluriel(i.questions, 'question')} de collègues en ${i.fenetre_jours} jours.`,
      texte: 'Faites-les connaître : un lien dans un message d\'équipe suffit souvent.',
    }
  }
  if (i.actives > 0) {
    return {
      titre: 'Vos collections sont prêtes : faites-les connaître.',
      texte: 'Aucun collègue ne les a encore interrogées. Partagez leur lien avec votre équipe.',
    }
  }
  return {
    titre: 'Votre collection est presque là.',
    texte: 'Terminez sa vérification pour la partager avec vos collègues.',
  }
}

export interface IndicateursCollection {
  questions: number
  /** Part des avis positifs, en pourcentage arrondi ; null sans avis. */
  satisfaction: number | null
  avis: number
  signalements: number
}

/** Les chiffres d'une carte de « Mes collections » : l'usage (bilan du serveur) et la note des usagers. */
export function indicateursCollection (
  usage: { questions: number, signalements_ouverts: number },
  col: Pick<Collection, 'avis'> | null | undefined,
): IndicateursCollection {
  const total = col?.avis?.total || 0
  const taux = col?.avis?.satisfaction_rate
  return {
    questions: usage.questions,
    satisfaction: total && taux !== null && taux !== undefined ? Math.round(taux * 100) : null,
    avis: total,
    signalements: usage.signalements_ouverts || 0,
  }
}
