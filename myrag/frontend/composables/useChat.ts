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
import type { AvisResana } from '~/utils/resana'
import { ref } from 'vue'
import { sansMention } from '~/utils/playground'
import { avisDeReponse } from '~/utils/resana'

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
  /** Invitations glissées dans la réponse (index Résana ancien ou incomplet). */
  avis?: AvisResana[]
  /** La mention que le serveur met en tête d'une réponse (« en cours de vérification »), à part. */
  mention?: string | null
}

export interface OptionsChat {
  /** Retirer la mention du texte de la réponse : l'écran l'explique ailleurs (étape 4 de l'assistant). */
  sansMention?: boolean
}

export function useChat(collection: string, options: OptionsChat = {}) {
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
        content: (options.sansMention ? sansMention(data.response || '', data.mention) : data.response) || 'Pas de réponse générée.',
        mention: data.mention || null,
        sources: data.sources || [],
        sourceNames: data.source_names || [],
        model: data.model,
        fallbackUsed: !!data.fallback_used,
        turnId: `turn-${Date.now()}`,
        avis: avisDeReponse(data.avis),
      }
      messages.value.push(assistant)
      return assistant
    } catch (e: any) {
      const errMsg = messageErreur(e)
      lastError.value = errMsg
      const errTurn: ChatMessage = {
        role: 'assistant',
        content: `La question n'a pas pu aboutir : ${errMsg}`,
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
