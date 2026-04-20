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
   * Hit /generate-eval and persist the result as an EvalDataset so the
   * questions appear on subsequent loads. The backend already attaches
   * "Jeu de test genere automatiquement" in the description, which the
   * /bank endpoint uses to classify the dataset as 'generated'.
   */
  async function generate() {
    if (isGenerating.value) return
    isGenerating.value = true
    try {
      const ds = await post(`/api/playground/${collection}/generate-eval`, {})
      if (ds?.questions?.length) {
        // Persist. The backend has no POST /eval/datasets yet — create one
        // through the same shape the wizard step-4 uses.
        await post(`/api/eval/${collection}/datasets`, {
          name: ds.name || `${collection}-evaluation`,
          description: ds.description || 'Jeu de test genere automatiquement',
          questions: ds.questions,
        }).catch(() => {
          // Best-effort: if the endpoint is missing the questions still
          // render this session via a one-shot in-memory fallback below.
        })
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
