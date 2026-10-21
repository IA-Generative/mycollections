/**
 * Le réseau d'entraide : ce que les écrans disent des appels, en fonctions pures testées.
 * Vocabulaire simple — « appel », « répondre », « collègues » — jamais « ticket ».
 */
import type { Capacites } from './capacites'

export type TypeAppel = 'donnee' | 'cherche' | 'propose'

export const LIBELLES_TYPE: Record<TypeAppel, { libelle: string, badge: string, invite: string }> = {
  donnee: { libelle: 'Il manque une donnée', badge: 'fr-badge--blue-ecume', invite: 'Dites que vous aussi en avez besoin.' },
  cherche: { libelle: 'Je cherche quelqu’un', badge: 'fr-badge--purple-glycine', invite: 'Vous connaissez ce sujet ? Répondez.' },
  propose: { libelle: 'Je propose mon aide', badge: 'fr-badge--green-menthe', invite: 'Cette aide vous intéresse ? Répondez.' },
}

export const LIBELLES_ETAT_APPEL: Record<string, { libelle: string, badge: string }> = {
  brouillon: { libelle: 'Brouillon', badge: 'fr-badge--new' },
  publie: { libelle: 'Ouvert', badge: 'fr-badge--success' },
  clos: { libelle: 'Clos', badge: '' },
}

/** Les types qu'une personne rédige ici : une donnée qui manque se demande depuis les demandes. */
export const TYPES_REDIGES: TypeAppel[] = ['cherche', 'propose']

/**
 * Où mène « /demandes » : au réseau d'entraide s'il est allumé, sinon la page reste la même.
 * Le formulaire de dépôt (`?deposer=1`) reste sur les demandes : c'est lui que le réseau ouvre.
 */
export function destinationDemandes (c: Pick<Capacites, 'entraide'>, requete: Record<string, unknown> = {}): '/entraide' | '/demandes' {
  return c.entraide === true && requete.deposer !== '1' ? '/entraide' : '/demandes'
}

/** Où ouvrir un appel : une demande en référence s'ouvre sur sa page, un appel sur la sienne. */
export function adresseAppel (a: { id: string, demande_id?: string | null, par_reference?: boolean }): string {
  return a.par_reference && a.demande_id ? `/demandes/${a.demande_id}` : `/entraide/${a.id}`
}

export function libelleType (t: string): string {
  return LIBELLES_TYPE[t as TypeAppel]?.libelle ?? t
}

/** « 1 réponse », « 3 réponses », « aucune réponse » ; pour une demande, ce sont des collègues intéressés. */
export function compteReponses (a: { nb_reponses: number, par_reference?: boolean }): string {
  const n = a.nb_reponses
  if (a.par_reference) {
    return n === 0 ? 'aucun collègue intéressé' : `${n} collègue${n > 1 ? 's' : ''} intéressé${n > 1 ? 's' : ''}`
  }
  return n === 0 ? 'aucune réponse' : `${n} réponse${n > 1 ? 's' : ''}`
}

export interface Recommandations {
  collections: { id: string, titre: string, description: string, vers: string }[]
  assistants: { id: string, titre: string, description: string, vers: string }[]
  demandes_voisines: { demande_id: string, titre: string, vers: string, roles: Record<string, number> }[]
}

/** Vrai quand le réseau n'a rien à montrer : l'écran n'affiche alors pas « Ceci existe peut-être déjà ». */
export function sansRecommandation (r: Recommandations | null): boolean {
  return !r || (r.collections.length + r.assistants.length + r.demandes_voisines.length === 0)
}

/** Les rôles de ceux qui ont soutenu une demande voisine, sans identité : « 2 soutiens, 1 fournisseur ». */
export function libelleRoles (roles: Record<string, number>): string {
  const pluriel: Record<string, string> = { soutien: 'soutiens', fournisseur: 'fournisseurs', relecteur: 'relecteurs', garant: 'garants' }
  const parts = Object.entries(roles).map(([role, n]) => `${n} ${n > 1 ? (pluriel[role] ?? role) : role}`)
  return parts.length ? parts.join(', ') : 'personne encore'
}
