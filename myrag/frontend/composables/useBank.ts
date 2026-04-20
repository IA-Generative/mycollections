/**
 * Test-question bank state for a single collection.
 *
 * Wraps GET /api/playground/{col}/bank + the write paths (feedback ingest,
 * promote, qr-cache add) so the playground page can reload the aggregated
 * view after every vote without caring about which backend table the
 * question actually came from.
 *
 * Auto-seed rule: if the bank is empty on first load, call /generate-eval
 * once to produce a fresh dataset — otherwise the page shows no guidance.
 * The user answered "oui au 1er chargement" in the design review, so this
 * runs without asking, and the user still controls further generations via
 * the explicit "Generate more" button.
 */
import { ref, computed } from 'vue'

export type BankSource = 'generated' | 'imported' | 'fb_neg' | 'promoted'

export interface BankItem {
  id: string
  question: string
  expected_answer?: string
  source: BankSource
  metadata: Record<string, any>
}

export interface BankStats {
  total: number
  generated: number
  imported: number
  fb_neg: number
  promoted: number
}

export function useBank(collection: string) {
  const { get, post, del } = useApi()

  const items = ref<BankItem[]>([])
  const stats = ref<BankStats>({ total: 0, generated: 0, imported: 0, fb_neg: 0, promoted: 0 })
  const isLoading = ref(false)
  const isGenerating = ref(false)
  const filter = ref<BankSource | 'all'>('all')

  const filtered = computed(() =>
    filter.value === 'all' ? items.value : items.value.filter(i => i.source === filter.value),
  )

  async function load() {
    isLoading.value = true
    try {
      const data = await get(`/api/playground/${collection}/bank`)
      items.value = data.items || []
      stats.value = data.stats || stats.value
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Generate fresh test questions and persist them as an EvalDataset so
   * subsequent loads see them classified as 'generated'.
   *
   * We deliberately use /chat with a list-producing prompt rather than
   * /generate-eval. The latter depends on an OpenRAG internal endpoint
   * (get_file_content) that 400s on a number of partitions, leaving the
   * bank permanently empty on those collections. /chat uses the public
   * RAG pipeline and works anywhere the playground itself works.
   */
  async function generate() {
    if (isGenerating.value) return
    isGenerating.value = true
    try {
      const data = await post(`/api/playground/${collection}/chat`, {
        question:
          "Propose 4 questions variees qu'un utilisateur pourrait poser sur le contenu indexe " +
          "de cette collection, pour tester le RAG. Reponds UNIQUEMENT avec les 4 questions, " +
          "une par ligne, sans numerotation, sans puces, sans introduction, sans conclusion. " +
          "Chaque question doit etre specifique au contenu reel, pas generique.",
        temperature: 0.4,
        top_k: 5,
      })
      const raw = (data?.response || '').trim()
      const questions = raw
        .split('\n')
        .map((line: string) =>
          line.replace(/^[\s\-\*\d\.\)•>]+/, '').replace(/[\s—-]+$/, '').trim(),
        )
        .filter((line: string) => line.length > 5 && line.includes('?'))
        .slice(0, 4)
        .map((q: string, i: number) => ({ id: `auto-${Date.now()}-${i}`, question: q, expected_answer: '' }))

      if (questions.length) {
        await post(`/api/eval/${collection}/datasets`, {
          name: `${collection}-evaluation`,
          description: 'Jeu de test genere automatiquement',
          questions,
        }).catch(() => { /* non-fatal: load() will just show nothing new */ })
      }
      await load()
    } finally {
      isGenerating.value = false
    }
  }

  async function autoSeedIfEmpty() {
    await load()
    if (stats.value.total === 0) {
      await generate()
    }
  }

  /**
   * 👍 vote. If the question was a Feedback row (fb_neg), promote it so
   * QRCache gets the curated answer. For generated/imported/promoted items,
   * add a new QRCache entry directly — those don't have a Feedback id to
   * promote from.
   */
  async function voteUp(item: BankItem, answer: string) {
    if (item.source === 'fb_neg' && item.metadata?.feedback_id) {
      await post(`/api/feedback/${collection}/${item.metadata.feedback_id}/promote`, {
        promote_to: 'qr',
        corrected_answer: answer,
      })
    } else {
      await post(`/api/qr-cache/${collection}`, {
        question: item.question,
        answer,
        source: 'manual',
      })
    }
    await load()
  }

  /**
   * 👎 vote. Always creates a new Feedback(rating=-1) so the collection
   * owner gets a ticket in the /c/{id} feedback tab. Even if the question
   * was already a Feedback row, we want a new entry capturing the new
   * bad response, because the old row references the old response.
   */
  async function voteDown(item: BankItem, response: string, reason = '') {
    await post(`/api/feedback/ingest`, {
      collection,
      question: item.question,
      response,
      rating: -1,
      reason,
    })
    await load()
  }

  async function removeItem(item: BankItem) {
    if (item.source === 'promoted' && item.metadata?.qr_id) {
      await del(`/api/qr-cache/${collection}/${item.metadata.qr_id}`).catch(() => {})
    } else if (item.source === 'generated' || item.source === 'imported') {
      // Deletes the whole dataset, which may contain other questions.
      // The UI warns the user before wiring this button up.
      if (item.metadata?.dataset_id) {
        await del(`/api/eval/${collection}/datasets/${item.metadata.dataset_id}`).catch(() => {})
      }
    }
    // fb_neg: never destructive from the bank (audit trail lives in /c/{id}).
    await load()
  }

  return {
    items,
    stats,
    filtered,
    filter,
    isLoading,
    isGenerating,
    load,
    generate,
    autoSeedIfEmpty,
    voteUp,
    voteDown,
    removeItem,
  }
}
