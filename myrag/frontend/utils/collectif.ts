/**
 * Le vocabulaire du collectif, côté écran — pur, testé sans navigateur.
 */
export const ETATS_COLLECTION = ['amorcee', 'en_controle', 'publiee_groupe', 'publiee_tous'] as const
export type EtatCollection = typeof ETATS_COLLECTION[number]

export const LIBELLES_ETAT: Record<string, string> = {
  amorcee: 'Amorcée',
  en_controle: 'En contrôle',
  publiee_groupe: 'Publiée au groupe',
  publiee_tous: 'Publiée à tous',
}

export const LIBELLES_DEMANDE: Record<string, { libelle: string; badge: string }> = {
  ouverte: { libelle: 'ouverte', badge: 'fr-badge--new' },
  chantier: { libelle: 'chantier', badge: 'fr-badge--info' },
  a_confirmer: { libelle: 'à confirmer', badge: 'fr-badge--warning' },
  realisee: { libelle: 'réalisée', badge: 'fr-badge--success' },
  close: { libelle: 'close', badge: '' },
}

export const FREQUENCES = [
  { valeur: 'quotidienne', libelle: 'Quotidienne' },
  { valeur: 'hebdomadaire', libelle: 'Hebdomadaire' },
  { valeur: 'mensuelle', libelle: 'Mensuelle' },
  { valeur: 'ponctuelle', libelle: 'Ponctuelle' },
]

/** Les rôles et leur coût en temps — ce que « Je peux aider » affiche et déclare. */
export const ROLES = [
  { valeur: 'soutien', libelle: 'soutien', cout: 'quelques secondes', minutes: 0 },
  { valeur: 'fournisseur', libelle: 'fournisseur', cout: '~2 h, une fois', minutes: 120 },
  { valeur: 'relecteur', libelle: 'relecteur', cout: '~1 h par relecture', minutes: 60 },
  { valeur: 'garant', libelle: 'garant', cout: '~2 h par mois', minutes: 120 },
]

/** L'auteur de la demande : un rôle tenu d'office, pas choisi — il n'est pas compté parmi les soutiens. */
export const ROLE_DEMANDEUR = { valeur: 'demandeur', libelle: 'demandeur', cout: '~½ h par semaine pendant le chantier' }

/** Ce que l'auteur a répondu à « la collection répond-elle à votre besoin ? ». */
export const LIBELLES_SATISFACTION: Record<string, string> = {
  oui: 'confirmée par le demandeur',
  non: 'ne répond pas encore au besoin',
  sans_reponse: 'réalisée sans confirmation du demandeur',
}

/** « dans 3 jours », « aujourd'hui » — l'échéance d'une demande à confirmer. */
export function echeance(iso: string | null | undefined, maintenant: Date = new Date()): string {
  if (!iso) return ''
  const jours = Math.ceil((new Date(iso).getTime() - maintenant.getTime()) / 86_400_000)
  if (jours <= 0) return "aujourd'hui"
  return jours === 1 ? 'demain' : `dans ${jours} jours`
}

export const MESSAGE_ACCES_ACTUEL =
  "Sans cette information, il nous est pratiquement impossible de constituer un nouveau jeu de données : c'est elle qui en révèle la source, le format et les conditions d'accès."

export function libelleEtat(etat: string | null | undefined): string {
  return LIBELLES_ETAT[etat || ''] || etat || '—'
}

export function indexEtat(etat: string | null | undefined): number {
  const i = ETATS_COLLECTION.indexOf((etat || 'amorcee') as EtatCollection)
  return i < 0 ? 0 : i
}

/** « 3 / 5 » et la largeur de la jauge, bornée à 100 %. */
export function progression(nb: number, seuil: number): { texte: string; pourcent: number; atteint: boolean } {
  const s = Math.max(1, seuil || 1)
  return { texte: `${nb} / ${s}`, pourcent: Math.min(100, Math.round((nb / s) * 100)), atteint: nb >= s }
}

/** Ce qui manque encore pour démarrer : le ET, jamais le OU. */
export function ceQuiManque(d: { nb_soutiens: number; seuil: number; garant: boolean; etat: string }): string | null {
  if (d.etat !== 'ouverte') return null
  const manques: string[] = []
  if (d.nb_soutiens < d.seuil) manques.push(`${d.seuil - d.nb_soutiens} soutien${d.seuil - d.nb_soutiens > 1 ? 's' : ''}`)
  if (!d.garant) manques.push('un garant')
  return manques.length ? `il manque ${manques.join(' et ')}` : null
}

export function libelleEvenement(type: string, detail: Record<string, any> = {}): string {
  const t: Record<string, string> = {
    'demande.creee': 'Demande déposée',
    'demande.modifiee': 'Demande modifiée',
    'soutien.ajoute': `Nouveau soutien${detail.role ? ` (${detail.role})` : ''}`,
    'soutien.retire': 'Soutien retiré',
    'garant.retire': 'Garant retiré par l’administration',
    'seuil.atteint': `Seuil atteint : ${detail.soutiens ?? '?'} soutiens et un garant`,
    'demande.etat': detail.satisfaction
      ? `${detail.satisfaction === 'oui' ? 'Le demandeur confirme : la collection répond' : detail.satisfaction === 'non' ? 'Le demandeur : ne répond pas encore' : `Sans réponse du demandeur en ${detail.jours ?? 5} jours`} — ${LIBELLES_DEMANDE[detail.vers]?.libelle || detail.vers}`
      : `Passage en ${LIBELLES_DEMANDE[detail.vers]?.libelle || detail.vers || '?'}`,
    'collection.creee': 'Collection créée',
    'collection.etat': `${detail.force ? 'Forçage : ' : ''}passage « ${libelleEtat(detail.de)} » → « ${libelleEtat(detail.vers)} »`,
    'grille.maj': 'Grille de contrôle mise à jour',
    'grille.relue': `Relecture (${detail.relecture_n ?? 1})`,
    'proposition.deposee': 'Proposition déposée',
    'proposition.publiee': 'Proposition publiée',
    'proposition.refusee': 'Proposition refusée',
    'signalement.depose': `Signalement (${detail.motif || '?'})`,
    'signalement.traite': `Signalement ${detail.vers || 'traité'}`,
    'publication.publiee': 'Publiée dans l’assistant',
    'publication.brouillon': 'Brouillon de publication',
    'publication.retiree': 'Retirée de l’assistant',
    'collection.archivee': 'Archivée',
    'collection.desarchivee': 'Désarchivée',
    'collection.purgee': 'Collection purgée',
    'import.termine': 'Import terminé',
    'import.echoue': 'Import échoué',
    'synchro.terminee': 'Synchronisation terminée',
    'source.enregistree': 'Source enregistrée',
  }
  return t[type] || type
}

/** Le détail chiffré d'un événement, en une ligne lisible. */
export function chiffres(detail: Record<string, any> = {}): string {
  const cles: [string, string][] = [
    ['lignes_importees', 'lignes'], ['documents', 'documents'], ['fichiers', 'fichiers'], ['morceaux', 'morceaux'],
    ['questions_testees', 'questions testées'], ['taux', 'taux'], ['nb_soutiens', 'soutiens'], ['temps_declare_min', 'min déclarées'],
  ]
  return cles.filter(([k]) => detail[k] !== undefined && detail[k] !== null).map(([k, l]) => `${l} ${detail[k]}`).join(' · ')
}

export function dateCourte(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** Ce que les codes HTTP veulent dire pour une personne, quand l'API ne dit rien de mieux. */
const SENS_DES_CODES: Record<number, string> = {
  401: 'Votre session a expiré : rechargez la page pour vous reconnecter.',
  403: "Vous n'avez pas le droit de faire ce geste sur cette collection.",
  404: "Introuvable : la collection a peut-être été archivée, ou vous n'y avez pas accès.",
  413: 'Le fichier est trop volumineux.',
  415: "Ce type de fichier n'est pas pris en charge.",
  429: 'Le service est très sollicité : réessayez dans une minute.',
  500: "Le service a rencontré une erreur. Réessayez ; si elle revient, dites-le dans « Mon avis ».",
  502: 'Un service dont nous dépendons ne répond pas. Réessayez dans un instant.',
  503: 'Le service est momentanément indisponible. Réessayez dans un instant.',
  504: 'Le service a mis trop de temps à répondre. Réessayez dans un instant.',
}

/** Le message d'erreur de l'API, débarrassé de son enveloppe JSON, en français lisible :
 *  le `detail` de l'API s'il est écrit pour une personne, sinon le sens du code HTTP. */
export function messageErreur(e: unknown): string {
  const brut = e instanceof Error ? e.message : String(e)
  if (/Failed to fetch|NetworkError|Load failed/i.test(brut)) return 'Le service ne répond pas. Vérifiez votre connexion, puis réessayez.'
  const m = brut.match(/^API error (\d+): (.*)$/s)
  if (!m) return brut
  const code = Number(m[1])
  let detail = ''
  try {
    const j = JSON.parse(m[2])
    if (typeof j.detail === 'string') detail = j.detail
    else if (Array.isArray(j.detail)) detail = j.detail.map((x: any) => x.msg?.replace(/^Value error, /, '') || '').join(' ')
  } catch {}
  // Un détail technique (anglais, trace, « Not Found ») ne parle à personne : le sens du code à la place.
  const technique = !detail || /^(Not Found|Internal Server Error|Unauthorized|Forbidden|Bad Request)$/i.test(detail)
    || /Traceback|Exception|Error:|not found$/i.test(detail)
  if (technique) return SENS_DES_CODES[code] || `Le service a répondu par une erreur (${code}). Réessayez dans un instant.`
  return detail
}
