<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li><a class="fr-breadcrumb__link" aria-current="page">Tester</a></li>
      </ol>
    </nav>

    <div class="myrag-playground">
      <!-- LEFT: chat column -->
      <section class="myrag-playground__chat">
        <!-- Empty state: invite to pick from bank or type -->
        <div v-if="!messages.length" class="myrag-playground__empty">
          <p v-if="bank.items.value.length" class="fr-text--sm">
            Clique sur une question a droite, ou tape la tienne ci-dessous.
          </p>
          <p v-else-if="bank.isGenerating.value" class="fr-text--sm">
            Preparation des premieres questions de test…
          </p>
          <p v-else class="fr-text--sm">
            Pose une question pour tester comment le RAG repond sur cette collection.
          </p>
        </div>

        <!-- Message list -->
        <div v-if="messages.length" class="myrag-playground__messages" ref="messagesEl">
          <PlaygroundChatMessage v-for="m in messages" :key="m.turnId || m.content"
                       :message="m"
                       @vote="(v) => onVote(m, v)" />
          <div v-if="isLoading" class="fr-text--sm" style="color:#666;padding:0.4rem 0;">
            ⏳ L'assistant reflechit…
          </div>
        </div>

        <!-- Input -->
        <div class="myrag-playground__input">
          <div class="fr-input-group">
            <label class="fr-label fr-sr-only" for="question">Votre question</label>
            <textarea id="question" class="fr-input" v-model="draft" rows="2"
                      placeholder="Ta question ici…"
                      @keydown.enter.exact.prevent="canSend && send()"></textarea>
          </div>
          <div class="fr-btns-group fr-btns-group--inline">
            <button class="fr-btn" @click="send" :disabled="!canSend">
              {{ isLoading ? 'Envoi…' : 'Envoyer' }}
            </button>
            <button class="fr-btn fr-btn--secondary" @click="reset" :disabled="!messages.length">
              Effacer
            </button>
          </div>
        </div>
      </section>

      <!-- RIGHT: bank column -->
      <aside class="myrag-playground__bank">
        <div class="myrag-playground__bank-header">
          <h2 class="fr-h5" style="margin:0;">Banque de questions</h2>
          <p class="fr-text--xs" style="color:#666;margin:0.2rem 0 0 0;">
            Questions venant des retours utilisateurs, d'un import, ou generees.
          </p>
        </div>

        <PlaygroundBankFilter v-model="bank.filter.value" :stats="bank.stats.value" />

        <!-- Loading / empty -->
        <p v-if="bank.isLoading.value && !bank.items.value.length" class="fr-text--sm" style="color:#666;">
          Chargement…
        </p>
        <p v-else-if="bank.isGenerating.value && !bank.items.value.length" class="fr-text--sm" style="color:#666;">
          Generation de questions de test…
        </p>
        <p v-else-if="!bank.filtered.value.length" class="fr-text--sm" style="color:#666;">
          Aucune question dans ce filtre.
        </p>

        <!-- Cards -->
        <div class="myrag-playground__bank-list">
          <PlaygroundBankCard v-for="q in bank.filtered.value" :key="q.id"
                    :item="q"
                    :tested="testedIds.has(q.id)"
                    :loading="isLoading"
                    @test="runFromBank(q)"
                    @remove="bank.removeItem(q)" />
        </div>

        <!-- Batch results table -->
        <div v-if="batchResults.length" class="myrag-playground__batch">
          <h3 class="fr-h6" style="margin:1rem 0 0.5rem;">Resultats batch ({{ batchResults.length }})</h3>
          <div class="fr-table fr-table--no-caption" style="margin-bottom:0;">
            <table>
              <thead>
                <tr><th>Question</th><th>Reponse</th><th>Sources</th></tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in batchResults" :key="i">
                  <td style="max-width:150px;font-size:0.78rem;">{{ trunc(r.question, 60) }}</td>
                  <td style="font-size:0.78rem;">{{ trunc(r.response, 100) }}</td>
                  <td style="font-size:0.78rem;">{{ r.source_count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Footer actions -->
        <div class="myrag-playground__bank-footer">
          <button class="fr-btn fr-btn--sm fr-btn--secondary"
                  :disabled="!bank.items.value.length || isBatchRunning"
                  @click="runAll">
            {{ isBatchRunning ? `⏳ ${batchProgress}/${bank.items.value.length}` : '▶▶ Lancer toute la banque' }}
          </button>
          <button class="fr-btn fr-btn--sm fr-btn--tertiary"
                  :disabled="bank.isGenerating.value"
                  @click="bank.generate">
            {{ bank.isGenerating.value ? '⏳ Generation…' : '🤖 Generer 4 de plus' }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useChat } from '~/composables/useChat'
import { useBank, type BankItem } from '~/composables/useBank'

const route = useRoute()
const id = route.params.id as string
const { post } = useApi()

const { messages, isLoading, sendMessage, reset: resetChat } = useChat(id)
const bank = useBank(id)

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)

/** Remember which bank items have been run through the chat this session,
 *  so the BankCard can switch its button label to "Re-tester". */
const testedIds = ref(new Set<string>())

/** Keep the bank item that originated each assistant turn so a 👍/👎 vote
 *  can call the right backend endpoint. Map is message.turnId → BankItem. */
const turnToBankItem = new Map<string, BankItem>()

const canSend = computed(() => !isLoading.value && draft.value.trim().length > 0)

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

async function send() {
  if (!canSend.value) return
  const q = draft.value.trim()
  draft.value = ''
  const assistant = await sendMessage(q)
  scrollToBottom()
  if (assistant?.turnId) {
    // Unlinked ad-hoc question — vote handler will create a QR/feedback with
    // only the question+answer, no bank link. Recorded as null.
    turnToBankItem.set(assistant.turnId, null as any)
  }
}

async function runFromBank(item: BankItem) {
  testedIds.value.add(item.id)
  const assistant = await sendMessage(item.question)
  scrollToBottom()
  if (assistant?.turnId) {
    turnToBankItem.set(assistant.turnId, item)
  }
}

function reset() {
  resetChat()
  testedIds.value.clear()
  turnToBankItem.clear()
}

async function onVote(msg: any, vote: 'up' | 'down') {
  const item = msg.turnId ? turnToBankItem.get(msg.turnId) : null
  if (item) {
    if (vote === 'up') await bank.voteUp(item, msg.content)
    else               await bank.voteDown(item, msg.content, '')
  } else {
    // Ad-hoc question — find the preceding user turn to capture the question.
    const idx = messages.value.indexOf(msg)
    const prev = idx > 0 ? messages.value[idx - 1] : null
    const question = prev?.content || ''
    if (!question) return
    if (vote === 'up') {
      await post(`/api/qr-cache/${id}`, {
        question, answer: msg.content, source: 'manual',
      })
    } else {
      await post(`/api/feedback/ingest`, {
        collection: id, question, response: msg.content, rating: -1,
      })
    }
    await bank.load()
  }
  // Reflect the vote on the message so VoteBar locks.
  msg.vote = vote
}

// Batch run — hits /chat for every item, accumulates a compact summary.
const batchResults = ref<{ question: string, response: string, source_count: number }[]>([])
const isBatchRunning = ref(false)
const batchProgress = ref(0)

async function runAll() {
  if (isBatchRunning.value || !bank.items.value.length) return
  isBatchRunning.value = true
  batchResults.value = []
  batchProgress.value = 0
  try {
    for (const q of bank.items.value) {
      try {
        const data = await post(`/api/playground/${id}/chat`, { question: q.question })
        batchResults.value.push({
          question: q.question,
          response: (data?.response || '').replace(/\s+/g, ' ').trim(),
          source_count: (data?.sources || []).length,
        })
      } catch (e: any) {
        batchResults.value.push({
          question: q.question,
          response: `Erreur: ${e?.message || e}`,
          source_count: 0,
        })
      }
      batchProgress.value += 1
    }
  } finally {
    isBatchRunning.value = false
  }
}

function trunc(s: string, n: number): string {
  if (!s) return ''
  return s.length > n ? s.substring(0, n) + '…' : s
}

onMounted(() => {
  bank.autoSeedIfEmpty()
})
</script>

<style>
/* Scoped inside the page — not scoped-to-component because we want the same
 * grid behavior to apply regardless of which slotted components render. */
.myrag-playground {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 1.5rem;
  align-items: start;
}
@media (max-width: 1200px) {
  .myrag-playground {
    grid-template-columns: 1fr;
  }
}

.myrag-playground__chat {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.myrag-playground__empty {
  padding: 0.6rem 0.8rem;
  background: #f6f6f6;
  border-left: 3px solid #dddddd;
  margin-bottom: 1rem;
  color: #555;
}
.myrag-playground__messages {
  max-height: 600px;
  overflow-y: auto;
  padding-right: 0.3rem;
  margin-bottom: 1rem;
}
.myrag-playground__input {
  position: sticky;
  bottom: 0;
  background: #fff;
  padding-top: 0.4rem;
}

.myrag-playground__bank {
  background: #fafafa;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 0.8rem 0.9rem;
  position: sticky;
  top: 1rem;
  max-height: calc(100vh - 2rem);
  overflow-y: auto;
}
.myrag-playground__bank-header { margin-bottom: 0.6rem; }
.myrag-playground__bank-list { min-height: 60px; }
.myrag-playground__bank-footer {
  margin-top: 0.8rem;
  padding-top: 0.6rem;
  border-top: 1px solid #e5e5e5;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
@media (max-width: 1200px) {
  .myrag-playground__bank {
    position: static;
    max-height: none;
  }
}
</style>
