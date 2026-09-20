/**
 * Consulter le corpus — fonctions pures de l'onglet « Documents », testées dans tests/unit.
 */

export interface DocumentCorpus {
  file_id: string
  titre: string
  fichier: string
  type: string
  taille: string
  url_source: string
}

export interface MorceauLu { id: string, texte: string, page: number | string | null }

export interface DocumentLu extends DocumentCorpus {
  contexte: string
  morceaux: MorceauLu[]
  total_morceaux: number
  illisibles: number
  tronque: boolean
}

const TYPES: Record<string, string> = {
  'text/markdown': 'Markdown',
  'text/plain': 'Texte',
  'text/html': 'HTML',
  'application/pdf': 'PDF',
  'application/msword': 'Word',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
}

/** « PDF » plutôt qu'« application/pdf » ; à défaut de type, l'extension du fichier. */
export function libelleType(d: Pick<DocumentCorpus, 'type' | 'fichier'>): string {
  if (TYPES[d.type]) return TYPES[d.type]
  const ext = (d.fichier.match(/\.([a-z0-9]{2,5})$/i) || [])[1]
  return ext ? ext.toUpperCase() : (d.type || '—')
}

/** Le texte d'un document, morceaux bout à bout ; un repère de page quand elle change. */
export function texteDuDocument(d: Pick<DocumentLu, 'morceaux'>): string {
  const parties: string[] = []
  let page: number | string | null = null
  for (const m of d.morceaux) {
    if (m.page !== null && m.page !== undefined && m.page !== page && d.morceaux.some(x => x.page !== m.page)) {
      parties.push(`*— page ${m.page} —*`)
    }
    page = m.page ?? page
    parties.push(m.texte.trim())
  }
  return parties.filter(Boolean).join('\n\n')
}

/** Ce que la lecture a laissé de côté, dit en clair ; chaîne vide quand tout a été lu. */
export function avertissementLecture(d: Pick<DocumentLu, 'morceaux' | 'total_morceaux' | 'illisibles' | 'tronque'>): string {
  if (!d.morceaux.length) return "Le texte de ce document n'a pas pu être relu."
  const dits: string[] = []
  if (d.tronque) dits.push(`Document long : seuls les ${d.morceaux.length} premiers passages sur ${d.total_morceaux} sont affichés.`)
  if (d.illisibles) dits.push(`${d.illisibles} passage${d.illisibles > 1 ? "s n'ont" : " n'a"} pas pu être relu${d.illisibles > 1 ? 's' : ''}.`)
  return dits.join(' ')
}

/** « 1–50 sur 3 585 » ; « Aucun document » quand la recherche ne donne rien. */
export function libellePlage(r: { total: number, page: number, par_page: number }, n: number): string {
  if (!r.total) return 'Aucun document'
  const debut = (r.page - 1) * r.par_page + 1
  const mille = (x: number) => String(x).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  return `${mille(debut)}–${mille(debut + n - 1)} sur ${mille(r.total)}`
}
