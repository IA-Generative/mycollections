/**
 * Chat state for a single collection's playground.
 *
 * Owns the messages array and the in-flight loading flag. Delegates the
 * actual HTTP call to useApi so retry-on-401 and baseUrl handling are
 * consistent with the rest of the app.
 *
 * Exposes:
 * - messages (Ref)           : full conversation (user + assistant turns)
 * - isLoading (Ref)          : true while waiting on /chat
 * - lastError (Ref)          : last error message, or ''
 * - sendMessage(text)        : append user turn, call /chat, append assistant turn
 * - reset()                  : clear everything
 *
 * Each assistant turn carries its full debug payload (model, sources,
 * fallback_used) so the UI can reveal it progressively under each message
 * instead of keeping a separate "last debug" mirror.
 */
import { ref } from 'vue'

export interface ChatSource {
  original_filename?: string
  filename?: string
  content?: string
  page?: number | string
  file_url?: string
  chunk_url?: string
  [key: string]: any
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  sourceNames?: string[]
  model?: string
  fallbackUsed?: boolean
  error?: boolean
  /** Server-assigned id for tracking votes back to a specific turn. */
  turnId?: string
}

export function useChat(collection: string) {
  const { post } = useApi()

  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const lastError = ref('')

  async function sendMessage(text: string): Promise<ChatMessage | null> {
    const q = text.trim()
    if (!q || isLoading.value) return null

    messages.value.push({ role: 'user', content: q })
    isLoading.value = true
    lastError.value = ''

    try {
      const data = await post(`/api/playground/${collection}/chat`, { question: q })
      const assistant: ChatMessage = {
        role: 'assistant',
        content: data.response || 'Pas de reponse generee.',
        sources: data.sources || [],
        sourceNames: data.source_names || [],
        model: data.model,
        fallbackUsed: !!data.fallback_used,
        turnId: `turn-${Date.now()}`,
      }
      messages.value.push(assistant)
      return assistant
    } catch (e: any) {
      const errMsg = e?.message || String(e)
      lastError.value = errMsg
      const errTurn: ChatMessage = {
        role: 'assistant',
        content: `**Erreur** : ${errMsg}`,
        error: true,
      }
      messages.value.push(errTurn)
      return errTurn
    } finally {
      isLoading.value = false
    }
  }

  function reset() {
    messages.value = []
    lastError.value = ''
  }

  return { messages, isLoading, lastError, sendMessage, reset }
}
