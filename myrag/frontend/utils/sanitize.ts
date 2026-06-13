import { marked } from 'marked'
import DOMPurify from 'dompurify'

/**
 * Rend du Markdown non fiable (réponses LLM/RAG, datasets importés) en HTML
 * assaini. `marked` ne nettoie PAS le HTML : sans DOMPurify, un document
 * ingéré contenant `<img onerror=...>` s'exécuterait via `v-html`.
 *
 * SPA uniquement (ssr: false) → DOMPurify dispose toujours du DOM navigateur.
 */
export function renderMarkdownSafe(text: string | null | undefined): string {
  if (!text) return ''
  const html = marked.parse(text, { breaks: true }) as string
  return DOMPurify.sanitize(html)
}
