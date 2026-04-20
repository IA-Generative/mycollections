<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li aria-current="page">Playground</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Playground RAG — {{ id }}</h1>
    <p class="fr-text--sm" style="color:#666;">
      Mini-agent conversationnel pour tester les reponses RAG de cette collection.
    </p>

    <div class="fr-grid-row fr-grid-row--gutters">
      <!-- Left: Chat -->
      <div class="fr-col-7">
        <!-- Suggestions (cliquables) -->
        <div v-if="suggestions.length && !messages.length" class="fr-card fr-mb-2w">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h3 class="fr-card__title">💡 Questions suggerees</h3>
              <p class="fr-text--sm" style="color:#666;">
                Cliquez une suggestion pour l'envoyer, ou tapez la votre en bas.
              </p>
              <div class="fr-mt-1w">
                <button v-for="(s, i) in suggestions" :key="i"
                        class="fr-btn fr-btn--sm fr-btn--secondary fr-mb-1w fr-mr-1w"
                        style="white-space:normal;text-align:left;"
                        :disabled="sending"
                        @click="ask(s)">
                  {{ s }}
                </button>
              </div>
              <p v-if="loadingSuggestions" class="fr-text--xs fr-mt-1w" style="color:#666;">
                Generation des suggestions en cours...
              </p>
            </div>
          </div>
        </div>

        <!-- Messages -->
        <div v-if="messages.length" class="fr-card fr-mb-2w">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <div v-for="(m, i) in messages" :key="i" class="fr-mb-2w">
                <!-- User -->
                <div v-if="m.role === 'user'" class="myrag-msg myrag-msg--user">
                  <div class="myrag-msg__role">Vous</div>
                  <div class="myrag-msg__body">{{ m.content }}</div>
                </div>
                <!-- Assistant -->
                <div v-else class="myrag-msg myrag-msg--assistant">
                  <div class="myrag-msg__role">🤖 Assistant</div>
                  <div class="myrag-msg__body myrag-md-preview" v-html="renderMd(m.content)"></div>
                  <div v-if="m.sources?.length" class="fr-text--xs fr-mt-1w" style="color:#666;">
                    <strong>Sources :</strong> {{ m.sources.join(', ') }}
                  </div>
                  <p v-else-if="m.content && !m.error" class="fr-text--xs fr-mt-1w" style="color:#b34000;">
                    Aucune source retrouvee — le RAG n'a pas trouve de chunks pertinents.
                  </p>
                </div>
              </div>
              <div v-if="sending" class="fr-text--sm" style="color:#666;">
                ⏳ L'assistant reflechit...
              </div>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="fr-input-group">
          <label class="fr-label" for="question">Votre question</label>
          <textarea id="question" class="fr-input" v-model="question" rows="2"
                    placeholder="Quelles sont les conditions pour une carte de sejour vie privee ?"
                    @keydown.enter.exact.prevent="canSend && send()"></textarea>
          <p class="fr-hint-text">Entree pour envoyer, Maj+Entree pour retour a la ligne.</p>
        </div>
        <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
          <button class="fr-btn" @click="send" :disabled="!canSend">
            {{ sending ? 'Envoi...' : 'Envoyer' }}
          </button>
          <button class="fr-btn fr-btn--secondary" @click="clearChat" :disabled="!messages.length">
            Effacer l'historique
          </button>
          <button class="fr-btn fr-btn--tertiary" @click="regenSuggestions" :disabled="loadingSuggestions">
            {{ loadingSuggestions ? 'Chargement...' : 'Nouvelles suggestions' }}
          </button>
        </div>
      </div>

      <!-- Right: Debug panel -->
      <div class="fr-col-5">
        <h3 class="fr-h5">Debug</h3>

        <!-- Metrics -->
        <div v-if="lastDebug" class="fr-card fr-mb-2w">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <p class="fr-text--sm">
                <strong>Dernier appel :</strong>
                {{ lastDebug.model || '' }}
                <span v-if="lastDebug.fallback_used"> — fallback metadata</span>
              </p>
              <p v-if="lastDebug.sources?.length" class="fr-text--sm">
                Sources retrouvees : {{ lastDebug.sources.length }}
              </p>
            </div>
          </div>
        </div>

        <!-- Sources -->
        <div v-if="lastDebug?.sources?.length">
          <h4 class="fr-h6">Sources ({{ lastDebug.sources.length }})</h4>
          <div v-for="(chunk, i) in lastDebug.sources" :key="i" class="fr-mb-1w">
            <details class="fr-accordion">
              <summary class="fr-accordion__btn">
                {{ chunk.original_filename || chunk.filename || `Source ${i + 1}` }}
              </summary>
              <div class="fr-collapse">
                <p class="fr-text--sm" style="white-space:pre-wrap;">
                  {{ (chunk.content || '').substring(0, 500) }}{{ (chunk.content || '').length > 500 ? '...' : '' }}
                </p>
              </div>
            </details>
          </div>
        </div>

        <NuxtLink :to="`/c/${id}/graph`" class="fr-link fr-text--sm fr-mt-2w">
          Voir le graph de references →
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { marked } from 'marked'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  error?: boolean
}

const route = useRoute()
const id = route.params.id as string
const { post } = useApi()

const question = ref('')
const messages = ref<ChatMsg[]>([])
const sending = ref(false)
const lastDebug = ref<any>(null)

const suggestions = ref<string[]>([])
const loadingSuggestions = ref(false)

const canSend = computed(() => !sending.value && question.value.trim().length > 0)

function renderMd(text: string): string {
  if (!text) return ''
  return marked.parse(text, { breaks: true }) as string
}

async function send() {
  if (!canSend.value) return
  const q = question.value.trim()
  question.value = ''
  await ask(q)
}

/**
 * Send a question to the RAG pipeline and append both the user question and
 * the assistant reply to the conversation history. Suggestions disappear on
 * first turn (the UI already shows them only when messages is empty).
 */
async function ask(q: string) {
  if (!q.trim()) return
  messages.value.push({ role: 'user', content: q })
  sending.value = true
  try {
    const data = await post(`/api/playground/${id}/chat`, { question: q })
    const content = data.response || 'Pas de reponse generee.'
    messages.value.push({
      role: 'assistant',
      content,
      sources: data.source_names || [],
    })
    lastDebug.value = {
      model: data.model,
      fallback_used: data.fallback_used,
      sources: data.sources || [],
    }
  } catch (e: any) {
    messages.value.push({
      role: 'assistant',
      content: `**Erreur** : ${e.message || e}`,
      error: true,
    })
  } finally {
    sending.value = false
  }
}

function clearChat() {
  messages.value = []
  lastDebug.value = null
}

async function loadSuggestions() {
  loadingSuggestions.value = true
  try {
    const data = await post(`/api/playground/${id}/generate-eval`, {})
    const qs = (data?.questions || [])
      .filter((x: any) => !x.out_of_scope && x.question)
      .slice(0, 4)
      .map((x: any) => x.question)
    suggestions.value = qs
  } catch {
    // Best-effort. generate-eval requires the collection to have content;
    // on empty/unindexed collections it 400s — the UI just shows nothing.
    suggestions.value = []
  } finally {
    loadingSuggestions.value = false
  }
}

async function regenSuggestions() {
  await loadSuggestions()
}

onMounted(loadSuggestions)
</script>

<style>
.myrag-msg {
  padding: 0.8rem 1rem;
  border-radius: 6px;
}
.myrag-msg--user {
  background: #eef3ff;
  border-left: 3px solid #6a6af4;
}
.myrag-msg--assistant {
  background: #f6f6f6;
  border-left: 3px solid #18753c;
}
.myrag-msg__role {
  font-size: 0.75rem;
  font-weight: 600;
  color: #555;
  margin-bottom: 0.3rem;
}
.myrag-msg__body {
  font-size: 0.95rem;
  line-height: 1.5;
}
.myrag-md-preview p:first-child { margin-top: 0; }
.myrag-md-preview p:last-child { margin-bottom: 0; }
.myrag-md-preview ul, .myrag-md-preview ol {
  padding-left: 1.2rem;
  margin: 0.4rem 0;
}
.myrag-md-preview code {
  background: #e8e8e8;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 0.85em;
}
.myrag-md-preview pre {
  background: #282c34;
  color: #f0f0f0;
  padding: 0.6rem 0.8rem;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.82em;
}
.myrag-md-preview pre code { background: transparent; padding: 0; }
</style>
