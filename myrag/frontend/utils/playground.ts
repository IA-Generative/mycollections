/**
 * Small shared helpers used across the playground UI.
 *
 * prettyName: turn a raw indexed filename into something a human can scan.
 *   The corpus pipeline stamps every file with a long
 *   "export_mirai___..._base_de_connaissance_<slug>" prefix plus an
 *   extension. Strip the prefix, drop the extension, collapse the triple
 *   underscores the DSFR exports use as separators. Keep the original if
 *   the cleaned version would be too short to be useful.
 *
 * toHttps: force any bare http:// URL to https://. OpenRAG emits chunk and
 *   file URLs over plain http even when served behind a TLS-terminating
 *   Traefik ingress; the browser then blocks the link as mixed-content.
 */
export function prettyName(raw: string | undefined | null): string {
  if (!raw) return ''
  let s = raw.replace(/\.[a-z0-9]{2,5}$/i, '')               // drop .txt/.pdf/.docx
  s = s.replace(/^.*?base_de_connaissance_[^_.]*[._]?/i, '') // drop pipeline prefix
  s = s.replace(/___+|_{2,}/g, ' · ').replace(/_/g, ' ')     // underscores → spaces
  s = s.replace(/\s+/g, ' ').trim()
  return s.length < 8 ? raw : s
}

export function toHttps(url: string | undefined | null): string {
  if (!url) return ''
  return url.replace(/^http:\/\//i, 'https://')
}

/**
 * Rewrite an OpenRAG source URL so it goes through the MyRAG proxy.
 *
 * OpenRAG's /extract/, /file/, and /static/ endpoints all require a
 * Bearer admin token. Links opened in a new browser tab can't attach that
 * header and end up on a 401 or a redirect to /auth/login. Same-origin
 * proxy endpoints on MyRAG carry the token server-side, and the browser
 * sees plain content (HTML-wrapped chunk text, or raw PDF/image).
 *
 * Safe no-op for anything that isn't recognized as an OpenRAG URL.
 */
export function proxiedSourceUrl(url: string | undefined | null): string {
  if (!url) return ''
  const https = toHttps(url)
  // /static/<file> serves the original document.
  const staticM = https.match(/\/static\/(.+)$/i)
  if (staticM) return `/api/openrag/static/${staticM[1]}`
  // /extract/<id> or /file/<id> serves a chunk or the file metadata.
  const m = https.match(/\/(extract|file)\/([^/?#]+)/i)
  if (m) return `/api/openrag/${m[1]}/${m[2]}`
  return https
}
