/**
 * Test-question bank state for a single collection.
 *
 * Wraps GET /api/playground/{col}/bank + the write paths (feedback ingest,
 * promote, qr-cache add) so the playground page can reload the aggregated
 * view after every vote without caring about which backend table the
 * question actually came from.
 *
 * Auto-seed rule: if the bank is empty on first load, run generate() once to
 * produce a fresh dataset — otherwise the page shows no guidance.
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
  const { get, post, patch, del } = useApi()

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
   * Uses /chat with a list-producing prompt: it rides the public RAG
   * pipeline and works anywhere the playground itself works, so the
   * seeded bank never depends on an internal endpoint.
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
        // Au jeu de questions de la collection (à relire : elles n'ont pas encore de réponse).
        await post(`/api/collections/${collection}/qualite/questions/import`, {
          questions, origine: 'generee',
        }).catch(() => { /* non bloquant : load() n'affichera simplement rien de nouveau */ })
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
    const racine = `/api/collections/${collection}/qualite/questions`
    if (item.source === 'fb_neg' && item.metadata?.feedback_id) {
      // L'avis devient une question du jeu, avec la réponse jugée bonne.
      await post(`${racine}/depuis-avis/${item.metadata.feedback_id}`, { reponse: answer }).catch(() => {})
    } else if (item.metadata?.question_id) {
      // La question est validée ; sans réponse de référence, elle prend celle-ci.
      await patch(`${racine}/${item.metadata.question_id}`, {
        relecture: 'valide', ...(item.expected_answer ? {} : { reponse: answer }),
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
    // Une question se retire seule (avant : tout le jeu de test qui la contenait partait avec).
    if (item.metadata?.question_id) {
      await del(`/api/collections/${collection}/qualite/questions/${item.metadata.question_id}`).catch(() => {})
    }
    // fb_neg : jamais supprimé depuis la banque (l'avis reste lisible dans la page Qualité).
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
