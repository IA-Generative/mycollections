/**
 * Déposer des documents dans une collection : ce qui est accepté, comment un dossier se trie,
 * comment un fichier se nomme. Fonctions pures, testées (tests/unit/depot.test.ts) ; le pendant
 * serveur est app/services/formats.py.
 *
 * Chaque fichier accepté part entier vers OpenRAG, qui le lit et le découpe lui-même en
 * passages (ADR-0005). Le CSV et l'extension .markdown n'y sont pas lus : refusés au dépôt
 * (« convertissez en .txt ou .md »).
 */

export const EXTENSIONS_TEXTE = ['.txt', '.md']
export const EXTENSIONS_DOCUMENT = ['.pdf', '.docx', '.doc', '.pptx', '.eml', '.png', '.jpg', '.jpeg']
export const ACCEPT = [...EXTENSIONS_TEXTE, ...EXTENSIONS_DOCUMENT].join(',')
export const FORMATS_LISIBLES = 'texte (.txt, .md), PDF, Word (.docx, .doc), PowerPoint (.pptx), courriel (.eml), images (.png, .jpg)'
export const TAILLE_MAX = 50 * 1024 * 1024

export type Nature = 'texte' | 'document'

const SEPARATEUR_DE_CHEMIN = /[\\/]/

export function extension (nom: string): string {
  const base = (nom || '').split(SEPARATEUR_DE_CHEMIN).pop() || ''
  const i = base.lastIndexOf('.')
  return i > 0 ? base.slice(i).toLowerCase() : ''
}

export function natureFichier (nom: string): Nature | null {
  const ext = extension(nom)
  if (EXTENSIONS_DOCUMENT.includes(ext)) {
    return 'document'
  }
  if (EXTENSIONS_TEXTE.includes(ext)) {
    return 'texte'
  }
  return null
}

/**
 * Le nom sous lequel un fichier d'un dossier est déposé : son chemin DANS le dossier choisi, les
 * sous-dossiers joints par « -- » (le serveur ne garde qu'un nom de fichier, et deux « notes.md »
 * de deux sous-dossiers ne doivent pas s'écraser). « Dossier/RH/notes.md » → « RH--notes.md ».
 */
export function nomDepuisChemin (chemin: string): string {
  const parties = (chemin || '').split(SEPARATEUR_DE_CHEMIN).filter(Boolean)
  if (parties.length <= 1) {
    return parties[0] || ''
  }
  return parties.slice(1).join('--')
}

export interface Candidat { nom: string, taille: number, chemin?: string }
export interface Ecart { nom: string, raison: string }

/** Ce qui sera déposé, et ce qui est écarté avec la raison (rien n'est écarté en silence). */
export function trier<T extends Candidat> (fichiers: T[]): { retenus: (T & { nomDepot: string, nature: Nature })[], ecartes: Ecart[] } {
  const retenus: (T & { nomDepot: string, nature: Nature })[] = []
  const ecartes: Ecart[] = []
  const vus = new Set<string>()
  for (const f of fichiers) {
    const affiche = f.chemin || f.nom
    const base = (affiche.split(SEPARATEUR_DE_CHEMIN).pop() || '')
    if (base.startsWith('.') || affiche.split(SEPARATEUR_DE_CHEMIN).some(p => p.startsWith('.') && p.length > 1)) {
      ecartes.push({ nom: affiche, raison: 'fichier caché' })
      continue
    }
    const nature = natureFichier(base)
    if (!nature) {
      ecartes.push({ nom: affiche, raison: 'format non pris en charge' })
      continue
    }
    if (f.taille === 0) {
      ecartes.push({ nom: affiche, raison: 'fichier vide' })
      continue
    }
    if (f.taille > TAILLE_MAX) {
      ecartes.push({ nom: affiche, raison: 'plus de 50 Mo' })
      continue
    }
    const nomDepot = f.chemin ? nomDepuisChemin(f.chemin) : f.nom
    if (vus.has(nomDepot)) {
      ecartes.push({ nom: affiche, raison: 'en double' })
      continue
    }
    vus.add(nomDepot)
    retenus.push({ ...f, nomDepot, nature })
  }
  return { retenus, ecartes }
}

export type EtatDepot = 'attente' | 'envoi' | 'indexation' | 'indexe' | 'echec'
export const LIBELLES_DEPOT: Record<EtatDepot, string> = {
  attente: 'En attente',
  envoi: 'Envoi…',
  indexation: 'Indexation…',
  indexe: 'Indexé',
  echec: 'En échec',
}

/** L'état d'un dépôt d'après son travail d'ingestion (`/api/ingest/jobs/<id>`). */
export function etatDuTravail (job: { status: string, failed_chunks?: number, total_chunks?: number } | null): EtatDepot {
  if (!job) {
    return 'indexation'
  }
  if (job.status === 'done') {
    return 'indexe'
  }
  if (job.status === 'done_with_errors') {
    return (job.failed_chunks || 0) >= (job.total_chunks || 1) ? 'echec' : 'indexe'
  }
  if (job.status === 'interrupted') {
    return 'echec'
  }
  return 'indexation'
}

/** « 12 indexés, 1 en échec, 3 en cours ». */
export function bilan (etats: EtatDepot[]): string {
  const n = (e: EtatDepot) => etats.filter(x => x === e).length
  const parts: string[] = []
  if (n('indexe')) {
    parts.push(`${n('indexe')} indexé${n('indexe') > 1 ? 's' : ''}`)
  }
  if (n('echec')) {
    parts.push(`${n('echec')} en échec`)
  }
  const encours = n('attente') + n('envoi') + n('indexation')
  if (encours) {
    parts.push(`${encours} en cours`)
  }
  return parts.join(', ')
}

/** L'état d'un document déposé tel qu'on le dit à l'étape « Documents » de l'assistant. */
export type EtatAffiche = 'pret' | 'decoupage' | 'attente' | 'echec'

const LIBELLES_ETAT_AFFICHE: Record<EtatAffiche, string> = {
  pret: 'prêt',
  decoupage: 'découpage en cours',
  attente: 'en attente',
  echec: 'en échec',
}

/**
 * L'état d'un travail d'ingestion (`/api/ingest/jobs/<id>`) : pas encore de travail = en attente ;
 *  découpage puis envoi au moteur = découpage en cours ; terminé = prêt (en échec si rien n'est passé).
 */
export function etatDepot (job: { status: string, failed_chunks?: number, total_chunks?: number } | null | undefined): EtatAffiche {
  if (!job) {
    return 'attente'
  }
  if (job.status === 'done') {
    return 'pret'
  }
  if (job.status === 'done_with_errors') {
    return (job.failed_chunks || 0) >= (job.total_chunks || 1) ? 'echec' : 'pret'
  }
  if (job.status === 'interrupted' || job.status === 'failed') {
    return 'echec'
  }
  return 'decoupage'
}

export function libelleEtatDepot (e: EtatAffiche): string {
  return LIBELLES_ETAT_AFFICHE[e]
}

/** L'état affiché d'un dépôt suivi par la zone de dépôt (`EtatDepot`). */
export function etatAfficheDepuis (e: EtatDepot): EtatAffiche {
  return ({ attente: 'attente', envoi: 'decoupage', indexation: 'decoupage', indexe: 'pret', echec: 'echec' } as const)[e]
}

/** « 312 passages », seulement quand le nombre est connu. */
export function passages (n: number | null | undefined): string | null {
  return typeof n === 'number' && n > 0 ? `${n} passage${n > 1 ? 's' : ''}` : null
}
