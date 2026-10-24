/**
 * Les réglages techniques d'une collection, dits en français.
 *
 * Les VALEURS (`auto`, `internal`, `generic`…) sont ce que stocke et lit l'API : elles ne
 * changent jamais. Seul ce qui s'AFFICHE passe par ici. Une valeur inconnue (un modèle de
 * consignes créé par un administrateur, une stratégie ajoutée plus tard) s'affiche telle
 * quelle plutôt que de disparaître.
 */

/** Comment les documents sont coupés en passages. */
export const LIBELLES_STRATEGIE: Record<string, string> = {
  auto: 'Découpage automatique',
  article: 'Découpage par article',
  section: 'Découpage par section',
  qr: 'Découpage par question-réponse',
  length: 'Découpage par longueur',
  chunk: 'Découpage par longueur',
  directory: 'Découpage par dossier',
}

/**
 * Les niveaux de sensibilité des documents, dans l'ordre des listes (#134 ; pendant backend :
 * `Sensitivity` dans `app/services/chunker.py`). Une collection Résana naît « Interne ».
 */
export const SENSIBILITES = [
  { valeur: 'public', libelle: 'Public — internet' },
  { valeur: 'internal', libelle: 'Interne' },
  { valeur: 'personal', libelle: 'Données personnelles' },
  { valeur: 'personal_sensitive', libelle: 'Données personnelles sensibles' },
  { valeur: 'controlled', libelle: 'Diffusion contrôlée' },
  { valeur: 'restricted', libelle: 'Diffusion restreinte' },
] as const

/** Le niveau de sensibilité des documents. */
export const LIBELLES_SENSIBILITE: Record<string, string> = Object.fromEntries(SENSIBILITES.map(s => [s.valeur, s.libelle]))

/** Les modèles de consignes données à l'assistant (clé `prompt_template`). */
export const LIBELLES_CONSIGNES: Record<string, string> = {
  generic: 'Consignes générales',
  juridique: 'Consignes juridiques',
  ceseda: 'Consignes droit des étrangers',
  multi_thematique: 'Consignes multi-thématiques',
  faq: 'Consignes questions-réponses',
  multimedia: 'Consignes multimédia',
  technique: 'Consignes documentation technique',
}

/** Ce que l'historique de publication a enregistré (`action`). */
export const LIBELLES_ACTION_PUBLICATION: Record<string, string> = {
  published: "Rendue disponible dans le chat MirAI",
  disabled: "Retirée du chat MirAI",
  archived: 'Archivée',
  unarchived: 'Désarchivée',
  draft: 'Brouillon',
}

function libelle(table: Record<string, string>, valeur?: string | null): string {
  if (!valeur) return ''
  return table[valeur] || valeur
}

export const libelleStrategie = (v?: string | null) => libelle(LIBELLES_STRATEGIE, v)
export const libelleSensibilite = (v?: string | null) => libelle(LIBELLES_SENSIBILITE, v)
export const libelleConsignes = (v?: string | null) => libelle(LIBELLES_CONSIGNES, v)
export const libelleActionPublication = (v?: string | null) => libelle(LIBELLES_ACTION_PUBLICATION, v)

/** L'état d'un avis laissé sur une réponse (`status`). */
export const LIBELLES_STATUT_AVIS: Record<string, string> = {
  pending: 'à relire',
  reviewed: 'relu',
  promoted: 'devenu question de référence',
}
export const libelleStatutAvis = (v?: string | null) => libelle(LIBELLES_STATUT_AVIS, v)
