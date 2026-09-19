/**
 * Mise en forme et export d'un extrait de source (morceau ou document complet),
 * pour la fenêtre de lecture ouverte depuis une puce de source.
 *
 * Deux exports, tous deux sans dépendance ni aller-retour serveur :
 * - Word : une page HTML servie en `application/msword` (.doc). Word et
 *   LibreOffice l'ouvrent avec titres, gras et listes — c'est le format d'échange
 *   HTML que Word lit nativement, pas un .docx.
 * - PDF : une fenêtre d'impression sur la même page ; le navigateur propose
 *   « Enregistrer au format PDF ». Pas de moteur PDF à embarquer côté serveur.
 */

export interface Extrait {
  titre: string
  sousTitre?: string
  meta: Array<[string, string]>
  /** Contenu textuel/Markdown brut de la source. */
  contenu: string
}

/** Lit la réponse brute d'OpenRAG (`/extract/<id>?raw=1`) quelle que soit sa forme :
 *  champs à plat, ou contenu + `metadata` imbriqué. */
export function lireExtrait(payload: any): { contenu: string, meta: Record<string, any> } {
  if (!payload || typeof payload !== 'object') return { contenu: '', meta: {} }
  const meta = { ...(payload.metadata || {}), ...payload }
  delete meta.metadata
  const contenu = payload.page_content ?? payload.content ?? payload.text ?? ''
  return { contenu: String(contenu), meta }
}

export interface Morceau {
  /** Résumé du document qu'OpenRAG place devant le morceau pour la recherche. */
  contexte: string
  /** Nom du fichier d'origine, tel que la ligne `* filename:` le donne. */
  fichier: string
  /** Le texte du morceau, sans ses balises techniques. */
  corps: string
}

/** Sépare un morceau relu dans OpenRAG de son habillage technique :
 *  `[CONTEXT] résumé  * filename: x.md  [CHUNK_START] texte [CHUNK_END]`.
 *  Le contenu reçu avec la réponse du chat n'a pas ces balises : il ressort tel quel. */
export function decouperMorceau(brut: string | null | undefined): Morceau {
  const texte = String(brut ?? '')
  const debut = texte.indexOf('[CHUNK_START]')
  if (debut < 0) {
    return { contexte: '', fichier: '', corps: texte.replace(/\[CHUNK_END\]\s*$/, '').trim() }
  }
  const apres = texte.slice(debut + '[CHUNK_START]'.length)
  const fin = apres.lastIndexOf('[CHUNK_END]')
  const corps = (fin < 0 ? apres : apres.slice(0, fin)).trim()

  let entete = texte.slice(0, debut).replace(/^\s*\[CONTEXT\]/, '')
  let fichier = ''
  entete = entete.replace(/^[ \t]*\*[ \t]*filename[ \t]*:[ \t]*(.*)$/mi, (_l, nom) => {
    fichier = String(nom).trim()
    return ''
  })
  return { contexte: entete.trim(), fichier, corps }
}

/** Nom de fichier sûr, sans accents ni ponctuation, borné à 80 caractères. */
export function nomDeFichier(titre: string, ext: string): string {
  const base = (titre || 'extrait')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/\.[a-z0-9]{2,5}$/i, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
    .slice(0, 80) || 'extrait'
  return `${base}.${ext}`
}

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** Page HTML autonome : sert à l'export Word comme à l'impression PDF.
 *  `corpsHtml` doit déjà être assaini (renderMarkdownSafe). */
export function pageAutonome(e: Extrait, corpsHtml: string, pourWord = false): string {
  const meta = e.meta.length
    ? `<p class="meta">${e.meta.map(([k, v]) => `<strong>${esc(k)}</strong> : ${esc(v)}`).join(' &middot; ')}</p>`
    : ''
  const sous = e.sousTitre ? `<p class="sous-titre">${esc(e.sousTitre)}</p>` : ''
  const wordNs = pourWord
    ? ' xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word"'
    : ''
  return `<!doctype html>
<html lang="fr"${wordNs}><head><meta charset="utf-8"><title>${esc(e.titre)}</title>
<style>
  @page { margin: 2cm; }
  body { font-family: Marianne, Arial, sans-serif; color: #161616; line-height: 1.5;
         font-size: 11pt; max-width: 800px; margin: 0 auto; }
  h1 { font-size: 18pt; margin: 0 0 4pt; color: #000091; }
  h2 { font-size: 14pt; margin: 14pt 0 4pt; }
  h3, h4 { font-size: 12pt; margin: 10pt 0 4pt; }
  .sous-titre { margin: 0 0 4pt; color: #3a3a3a; }
  .meta { font-size: 9pt; color: #666; margin: 0 0 12pt; padding-bottom: 8pt;
          border-bottom: 1px solid #ddd; }
  table { border-collapse: collapse; }
  th, td { border: 1px solid #ccc; padding: 3pt 6pt; }
  pre, code { font-family: Consolas, monospace; font-size: 9.5pt; }
  .pied { margin-top: 18pt; font-size: 8pt; color: #888; }
</style></head>
<body><h1>${esc(e.titre)}</h1>${sous}${meta}${corpsHtml}
<p class="pied">Extrait issu de Mes collections — ${esc(new Date().toLocaleDateString('fr-FR'))}</p>
</body></html>`
}
