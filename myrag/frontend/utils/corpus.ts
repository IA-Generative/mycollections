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
  /** Le document entier tel que l'indexeur l'a lu (#147), quand il en garde la copie. */
  markdown?: string
  fidele?: boolean
  /** Pourquoi la copie entière manque : `MARKDOWN_NOT_AVAILABLE` (indexé sans elle)… */
  fidele_raison?: string
  /** Lu par reconnaissance de caractères : le texte peut contenir des erreurs. */
  ocr?: boolean
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

const REPERE_PAGE = /<!--\s*page\s+(\d+)\s*-->/gi

/**
 * La copie entière de l'indexeur, ses repères `<!-- page N -->` rendus visibles (un document
 * d'une seule page n'en montre aucun). Le reste — titres, listes, tableaux HTML — passe tel quel
 * au rendu Markdown assaini.
 */
export function markdownFidele(md: string): string {
  const pages = new Set(Array.from(md.matchAll(REPERE_PAGE), m => m[1]))
  return md.replace(REPERE_PAGE, (_, n) => (pages.size > 1 ? `\n\n*— page ${n} —*\n\n` : '')).trim()
}

/**
 * Le texte d'un document : sa copie entière si l'indexeur la garde, sinon ses morceaux bout à
 * bout, avec un repère de page quand elle change.
 */
export function texteDuDocument(d: Pick<DocumentLu, 'morceaux'> & Partial<Pick<DocumentLu, 'markdown'>>): string {
  if (d.markdown) {
    return markdownFidele(d.markdown)
  }
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
export function avertissementLecture(
  d: Pick<DocumentLu, 'morceaux' | 'total_morceaux' | 'illisibles' | 'tronque'> & Partial<Pick<DocumentLu, 'markdown' | 'fidele_raison' | 'ocr'>>,
): string {
  const ocr = d.ocr ? 'Texte reconnu automatiquement (OCR) : il peut contenir des erreurs ; le document d\'origine fait foi.' : ''
  if (d.markdown) {
    return ocr
  }
  if (!d.morceaux.length) return "Le texte de ce document n'a pas pu être relu."
  const dits: string[] = []
  if (d.fidele_raison === 'MARKDOWN_NOT_AVAILABLE') {
    dits.push('Version intégrale indisponible : le texte est recomposé à partir des passages indexés. Une ré-indexation du document la rendra lisible en entier.')
  }
  if (ocr) {
    dits.push(ocr)
  }
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
