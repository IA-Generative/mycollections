/**
 * Ce que l'accueil raconte — fonctions pures, testées dans tests/unit.
 * L'accueil invite à découvrir, puis à partager ; il ne reproche rien à qui ne gère rien.
 */
import type { Categorie, Collection } from '~/types/collection'

export interface Indicateurs { collections: number; categories: number; documents: number }

/** Les trois chiffres de la tuile « Découvrir », sur ce que la personne peut réellement lire. */
export function indicateurs(collections: Collection[], categories: Categorie[]): Indicateurs {
  const lisibles = collections.filter(c => !c.orphan)
  const connues = new Set(categories.map(c => c.cle))
  return {
    collections: lisibles.length,
    categories: new Set(lisibles.map(c => c.categorie).filter((k): k is string => !!k && connues.has(k))).size,
    documents: lisibles.reduce((n, c) => n + (Number(c.file_count) || 0), 0),
  }
}

/** 31400 → « 31 400 » (espace fine insécable, comme on l'écrit en français). */
export function nombre(n: number): string {
  return String(Math.round(n || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
}

export interface Porte { cle: string; libelle: string; nb: number }

/** Les portes d'entrée du catalogue : les catégories non vides, dans l'ordre de l'administration. */
export function portes(collections: Collection[], categories: Categorie[]): Porte[] {
  return [...categories]
    .sort((a, b) => a.ordre - b.ordre)
    .map(k => ({ cle: k.cle, libelle: k.libelle, nb: collections.filter(c => !c.orphan && c.categorie === k.cle).length }))
    .filter(p => p.nb > 0)
}

export interface DemandeResumee { id: string; titre: string; etat: string; nb_soutiens: number; seuil: number; soutenue_par_moi?: boolean }

/** La demande à montrer « en ce moment » : ouverte, pas encore au seuil, la plus proche de l'atteindre
 *  (à égalité, la plus soutenue). Rien si aucune n'est ouverte — le bloc se masque. */
export function demandeEnVue(demandes: DemandeResumee[]): DemandeResumee | null {
  const ouvertes = demandes.filter(d => d.etat === 'ouverte' && d.nb_soutiens < d.seuil)
  if (!ouvertes.length) return null
  return [...ouvertes].sort((a, b) => (a.seuil - a.nb_soutiens) - (b.seuil - b.nb_soutiens) || b.nb_soutiens - a.nb_soutiens)[0]
}

export interface BilanPartage {
  collections: { name: string; titre: string; questions: number; publiee: boolean; signalements_ouverts: number }[]
  actives: number
  questions: number
  personnes: number | null
  signalements_ouverts?: number
  /** Mes propres questions sur la fenêtre : elles ne comptent pas, mais on les dit. */
  mes_essais?: number
  fenetre_jours: number
}

export interface Merci { titre: string; texte: string; action: { libelle: string; vers: string } }

/**
 * Le message à celui qui partage. Trois tons, jamais un reproche :
 *  - ses collections servent : on dit à quoi ;
 *  - elles ne sont pas encore interrogées : on l'aide à les faire connaître ;
 *  - rien n'est publié : on l'invite à finir.
 * `null` : la personne ne gère rien — pas de bandeau.
 */
export function messageMerci(b: BilanPartage | null): Merci | null {
  if (!b || !b.collections.length) return null
  const premiere = [...b.collections].sort((x, y) => y.questions - x.questions)[0]
  if (b.questions > 0) {
    const qui = b.personnes ? `${nombre(b.personnes)} collègue${b.personnes > 1 ? 's ont' : ' a'} trouvé une réponse` : 'Des collègues ont trouvé une réponse'
    return {
      titre: 'Vos collections travaillent pour vos collègues.',
      texte: `${qui} sans vous déranger — ni chercher. La plus consultée : « ${premiere.titre} ».`,
      action: { libelle: 'Partager une autre source', vers: '/admin/create' },
    }
  }
  if (b.actives > 0) {
    // « Personne » serait faux pour qui vient d'y poser six questions : on dit que ses essais ne comptent pas.
    const mes = b.mes_essais || 0
    const essais = mes > 1 ? `Vos ${nombre(mes)} essais ne comptent pas : aucun collègue ne les a encore interrogées`
      : mes === 1 ? 'Votre essai ne compte pas : aucun collègue ne les a encore interrogées'
      : 'Aucun collègue ne les a encore interrogées'
    return {
      titre: 'Vos collections sont prêtes — faites-les connaître.',
      texte: `${essais} ces ${b.fenetre_jours} derniers jours, depuis le bac à sable. Un lien dans un message d'équipe suffit souvent : « ${premiere.titre} » répond en langage courant.`,
      action: { libelle: 'Copier le lien à partager', vers: `/c/${premiere.name}` },
    }
  }
  return {
    titre: 'Votre collection est presque là.',
    texte: `« ${premiere.titre} » n'est pas encore publiée : une fois vérifiée, vos collègues pourront l'interroger.`,
    action: { libelle: 'Reprendre où j\'en étais', vers: `/c/${premiere.name}` },
  }
}
