<template>
  <div>
    <FilAriane :collection="id" :titre="titre" rubrique="Poser une question" />

    <div class="myrag-playground">
      <!-- LEFT: chat column -->
      <section ref="chatEl" class="myrag-playground__chat">
        <!-- Empty state: invite to pick from bank or type -->
        <div v-if="!messages.length" class="myrag-playground__empty">
          <p v-if="bank.items.value.length" class="fr-text--sm">
            Choisissez une question à droite, ou saisissez la vôtre ci-dessous.
          </p>
          <p v-else-if="bank.isGenerating.value" class="fr-text--sm">
            Préparation des premières questions de test…
          </p>
          <p v-else class="fr-text--sm">
            Posez une question pour voir comment la collection répond.
          </p>
        </div>

        <!-- Message list -->
        <div v-if="messages.length" class="myrag-playground__messages" ref="messagesEl">
          <PlaygroundChatMessage v-for="m in messages" :key="m.turnId || m.content" :gestionnaire="peutGerer"
                       :message="m"
                       @vote="(v) => onVote(m, v)" />
          <div v-if="isLoading" class="fr-text--sm myrag-playground__attente" role="status">
            ⏳ L'assistant réfléchit<span class="myrag-playground__points" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span>
          </div>
        </div>

        <!-- Input -->
        <div class="myrag-playground__input" :class="{ 'myrag-playground__input--frappe': enFrappe }">
          <div class="fr-input-group">
            <label class="fr-label fr-sr-only" for="question">Votre question</label>
            <textarea id="question" class="fr-input" v-model="draft" rows="2"
                      placeholder="Votre question…" :readonly="enFrappe"
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
          <p v-if="rechercheIndisponible" class="fr-message fr-message--info fr-mt-1w">
            Les questions reviendront dès que la recherche sera rétablie. Le bandeau en haut de la page vous préviendra.
          </p>
        </div>
      </section>

      <!-- RIGHT: bank column -->
      <aside class="myrag-playground__bank">
        <div class="myrag-playground__bank-header">
          <h2 class="fr-h5" style="margin:0;">Banque de questions</h2>
          <p class="fr-text--xs" style="color:#666;margin:0.2rem 0 0 0;">
            Questions venant des retours utilisateurs, d'un import, ou générées automatiquement.
          </p>
        </div>

        <PlaygroundBankFilter v-model="bank.filter.value" :stats="bank.stats.value" />

        <!-- Loading / empty -->
        <p v-if="bank.isLoading.value && !bank.items.value.length" class="fr-text--sm" style="color:#666;">
          Chargement…
        </p>
        <p v-else-if="bank.isGenerating.value && !bank.items.value.length" class="fr-text--sm" style="color:#666;">
          Génération de questions de test…
        </p>
        <p v-else-if="!bank.filtered.value.length" class="fr-text--sm" style="color:#666;">
          Aucune question dans ce filtre.
        </p>

        <!-- Cards -->
        <div class="myrag-playground__bank-list">
          <PlaygroundBankCard v-for="q in bank.filtered.value" :key="q.id"
                    :item="q"
                    :tested="testedIds.has(q.id)"
                    :loading="isLoading || enFrappe"
                    @test="runFromBank(q)"
                    @remove="bank.removeItem(q)" />
        </div>

        <!-- Batch results table -->
        <div v-if="batchResults.length" class="myrag-playground__batch">
          <h3 class="fr-h6" style="margin:1rem 0 0.5rem;">Résultats de toute la banque ({{ batchResults.length }})</h3>
          <div class="fr-table fr-table--no-caption" style="margin-bottom:0;">
            <table>
              <thead>
                <tr><th>Question</th><th>Réponse</th><th>Sources</th></tr>
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
                  :disabled="!bank.items.value.length || isBatchRunning || rechercheIndisponible"
                  title="Pose à la collection, l'une après l'autre, toutes les questions de la banque, et résume les réponses dans un tableau."
                  @click="runAll">
            {{ isBatchRunning ? `⏳ ${batchProgress}/${bank.items.value.length}` : '▶▶ Lancer toute la banque' }}
          </button>
          <button class="fr-btn fr-btn--sm fr-btn--tertiary"
                  :disabled="bank.isGenerating.value"
                  title="Fait rédiger automatiquement quatre nouvelles questions de test à partir des documents de la collection."
                  @click="bank.generate">
            {{ bank.isGenerating.value ? '⏳ Génération…' : '🤖 Générer 4 de plus' }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useChat } from '~/composables/useChat'
import { useBank, type BankItem } from '~/composables/useBank'
import { etapesDeFrappe } from '~/utils/playground'

const route = useRoute()
const id = route.params.id as string
const { titre } = useTitreCollection(id)
const { get, post } = useApi()

const { messages, isLoading, sendMessage, reset: resetChat } = useChat(id)
const bank = useBank(id)
/** Gérer la collection (dit par l'API) : 👍 l'ajoute alors aux réponses validées ; sinon, un avis. */
const peutGerer = ref(false)

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const chatEl = ref<HTMLElement | null>(null)
/** Une question de la banque s'écrit dans le champ avant de partir : on voit qu'elle est prise en compte. */
const enFrappe = ref(false)

/** Remember which bank items have been run through the chat this session,
 *  so the BankCard can switch its button label to "Re-tester". */
const testedIds = ref(new Set<string>())

/** Keep the bank item that originated each assistant turn so a 👍/👎 vote
 *  can call the right backend endpoint. Map is message.turnId → BankItem. */
const turnToBankItem = new Map<string, BankItem>()

// Une question posée pendant une panne échouerait : on le dit avant le clic.
const { rechercheIndisponible } = useEtatService()
const canSend = computed(() => !isLoading.value && !enFrappe.value && !rechercheIndisponible.value && draft.value.trim().length > 0)

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    amenerLaSaisie()
  })
}

async function send() {
  if (!canSend.value) return
  const q = draft.value.trim()
  draft.value = ''
  // Défiler dès l'envoi : la question et « L'assistant réfléchit… » se voient sans attendre la réponse.
  const envoi = sendMessage(q)
  scrollToBottom()
  const assistant = await envoi
  scrollToBottom()
  if (assistant?.turnId) {
    // Unlinked ad-hoc question — vote handler will create a QR/feedback with
    // only the question+answer, no bank link. Recorded as null.
    turnToBankItem.set(assistant.turnId, null as any)
  }
}

const attendre = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
const mouvementReduit = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Le bas de la conversation sous les yeux : le champ de saisie à sa place, les derniers messages
 *  juste au-dessus. Le champ reste collé en bas de l'écran (sticky) : sans ce défilement, sur petit
 *  écran, il recouvrirait la question qui vient de partir et « L'assistant réfléchit… ». */
function amenerLaSaisie() {
  const el = chatEl.value
  if (!el) return
  // Déjà en place : le bas de la conversation est dans l'écran, champ de saisie compris.
  const bas = el.getBoundingClientRect().bottom
  const saisie = (el.lastElementChild as HTMLElement | null)?.offsetHeight || 0
  if (bas <= window.innerHeight && bas >= saisie) return
  el.scrollIntoView({ behavior: mouvementReduit() ? 'auto' : 'smooth', block: 'end' })
}

/** La question choisie s'écrit dans le champ de saisie, que la page amène sous les yeux (sur petit
 *  écran, la banque est sous la conversation). Sans animation si la personne les a désactivées. */
async function taper(texte: string) {
  enFrappe.value = true
  try {
    amenerLaSaisie()
    if (mouvementReduit()) {
      draft.value = texte
      return
    }
    for (const n of etapesDeFrappe(texte.length)) {
      draft.value = texte.slice(0, n)
      await attendre(18)
    }
    await attendre(250)
  }
  finally {
    enFrappe.value = false
  }
}

async function runFromBank(item: BankItem) {
  if (isLoading.value || enFrappe.value) return
  testedIds.value.add(item.id)
  await taper(item.question)
  // La question quitte le champ et entre dans la conversation, avec « L'assistant réfléchit… » dessous.
  const envoi = sendMessage(item.question)
  draft.value = ''
  scrollToBottom()
  const assistant = await envoi
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
  if (!peutGerer.value) {
    // Un lecteur ne modifie pas la collection : son 👍 comme son 👎 devient un avis pour le gestionnaire.
    const idx = messages.value.indexOf(msg)
    const question = item?.question || (idx > 0 ? messages.value[idx - 1]?.content : '') || ''
    if (question) {
      await post(`/api/feedback/ingest`, { collection: id, question, response: msg.content, rating: vote === 'up' ? 1 : -1 })
    }
  } else if (item) {
    if (vote === 'up') await bank.voteUp(item, msg.content)
    else               await bank.voteDown(item, msg.content, '')
  } else {
    // Ad-hoc question — find the preceding user turn to capture the question.
    const idx = messages.value.indexOf(msg)
    const prev = idx > 0 ? messages.value[idx - 1] : null
    const question = prev?.content || ''
    if (!question) return
    if (vote === 'up') {
      // Une question libre jugée bien répondue entre au jeu de questions, validée.
      await post(`/api/collections/${id}/qualite/questions`, {
        question, reponse: msg.content, relecture: 'valide',
      }).catch(() => { /* déjà dans le jeu : rien à faire */ })
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
          response: messageErreur(e),
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

onMounted(async () => {
  // « Poser cette question » depuis l'accueil : la question arrive saisie, il reste à l'envoyer.
  // Avant tout appel : le champ ne doit pas rester vide le temps que l'API réponde.
  const q = String(route.query.q || '').trim()
  if (q && !draft.value) draft.value = q.slice(0, 500)
  // Les droits ensuite : seul qui gère la collection garnit sa banque et ses réponses validées.
  try { peutGerer.value = !!(await get(`/api/collections/${id}`))?.mes_droits?.ecrire } catch { peutGerer.value = false }
  if (peutGerer.value) bank.autoSeedIfEmpty()
  else bank.load().catch(() => {})
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
/* Une question de la banque s'écrit dans le champ : il s'éclaire le temps de la frappe. */
.myrag-playground__input--frappe .fr-input {
  box-shadow: inset 0 -2px 0 0 var(--border-active-blue-france), 0 0 0 3px var(--background-action-low-blue-france);
  transition: box-shadow 0.2s;
}
.myrag-playground__attente {
  color: #666;
  padding: 0.4rem 0;
}
.myrag-playground__points span {
  animation: myrag-point 1.2s infinite;
  opacity: 0.2;
}
.myrag-playground__points span:nth-child(2) { animation-delay: 0.2s; }
.myrag-playground__points span:nth-child(3) { animation-delay: 0.4s; }
@keyframes myrag-point {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .myrag-playground__points span { animation: none; opacity: 1; }
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
