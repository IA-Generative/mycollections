/**
 * Résana à l'écran (docs/resana.md) : lire les erreurs du service, dire où en est un import ou une
 * synchronisation. Fonctions pures, testées dans tests/unit/resana.test.ts.
 */

export interface ErreurResana {
  message: string
  code?: string
  /** La page de connexion à Résana que donne le service (https seulement). */
  urlConnexion?: string
  reessayable?: boolean
}

export interface TravailResana {
  etat?: 'en_cours' | 'termine' | 'a_jour' | 'echec' | 'interrompu' | string
  action?: 'import' | 'synchronisation' | string
  total?: number
  faits?: number
  ajoutes?: number
  modifies?: number
  retires?: number
  inchanges?: number
  ecartes?: number
  message?: string
  code?: string
  url_connexion?: string
  documents_ecartes?: { titre: string, raison: string }[]
}

export interface StatutResana {
  configured: boolean
  espace_nom?: string | null
  dossier_chemin?: string | null
  documents: number
  last_sync_at?: string | null
  travail?: TravailResana | null
  est_importeur: boolean
}

const ERREUR_API = /^API error (\d+): (.*)$/s
const REPLI = 'Le service Résana ne répond pas comme prévu. Réessayez dans un instant.'

function lienSur (url: unknown): string | undefined {
  return typeof url === 'string' && url.startsWith('https://') ? url : undefined
}

/** L'erreur levée par useApi (« API error 409: {…} »), en phrase et lien de connexion. */
export function erreurResana (brut: unknown): ErreurResana {
  const texte = brut instanceof Error ? brut.message : String(brut ?? '')
  const m = ERREUR_API.exec(texte)
  if (!m) {
    return { message: REPLI, reessayable: true }
  }
  const statut = Number(m[1])
  let detail: unknown
  try {
    detail = (JSON.parse(m[2] ?? '') as { detail?: unknown }).detail
  }
  catch {
    return { message: REPLI, reessayable: statut >= 500 }
  }
  if (typeof detail === 'string') {
    return { message: detail, reessayable: statut >= 500 }
  }
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>
    return {
      message: typeof d.message === 'string' && d.message ? d.message : REPLI,
      code: typeof d.code === 'string' ? d.code : undefined,
      urlConnexion: lienSur(d.url_connexion),
      reessayable: d.reessayable === true,
    }
  }
  return { message: REPLI, reessayable: statut >= 500 }
}

function compte (n: number | undefined, un: string, plusieurs: string): string {
  const v = n ?? 0
  return `${v} ${v > 1 ? plusieurs : un}`
}

/** Une phrase sur l'import ou la synchronisation en cours ou finie. */
export function libelleTravail (t: TravailResana | null | undefined): string {
  if (!t || !t.etat) {
    return ''
  }
  const feminin = t.action === 'synchronisation'
  const quoi = feminin ? 'Synchronisation' : 'Import'
  const e = feminin ? 'e' : ''
  switch (t.etat) {
    case 'en_cours':
      return t.total ? `${quoi} en cours : ${t.faits ?? 0} sur ${compte(t.total, 'document', 'documents')} lus.` : `${quoi} en cours.`
    case 'a_jour':
      return 'Rien n\'a changé dans Résana depuis la dernière synchronisation.'
    case 'termine': {
      const parties = [
        compte(t.ajoutes, 'ajouté', 'ajoutés'),
        compte(t.modifies, 'modifié', 'modifiés'),
        compte(t.retires, 'retiré', 'retirés'),
      ]
      const ecartes = t.ecartes ? `, ${compte(t.ecartes, 'écarté', 'écartés')}` : ''
      return `${quoi} terminé${e} : ${parties.join(', ')}${ecartes}. L'indexation se poursuit en tâche de fond.`
    }
    case 'interrompu':
      return `${quoi} interrompu${e} (le service a redémarré). Relancez la synchronisation.`
    case 'echec':
      return `${quoi} arrêté${e} : ${t.message || 'erreur du service Résana.'}`
    default:
      return ''
  }
}

export function travailEnCours (t: TravailResana | null | undefined): boolean {
  return t?.etat === 'en_cours'
}

/** « 40 documents, environ 120 Mo » — la taille de Résana est arrondie, on le dit. */
export function resumeApercu (a: { total: number, taille_approx_mo?: number | null }): string {
  const docs = compte(a.total, 'document', 'documents')
  if (typeof a.taille_approx_mo !== 'number') {
    return docs
  }
  const mo = a.taille_approx_mo < 1 ? 'moins de 1 Mo' : `environ ${Math.round(a.taille_approx_mo)} Mo`
  return `${docs}, ${mo}`
}
