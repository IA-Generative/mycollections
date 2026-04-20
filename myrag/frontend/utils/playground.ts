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
