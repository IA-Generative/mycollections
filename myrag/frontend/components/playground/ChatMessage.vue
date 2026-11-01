<script setup lang="ts">
import type { ChatMessage } from '~/composables/useChat'
import { numeroCitation } from '~/utils/assistants'
import { renderMarkdownSafe } from '~/utils/sanitize'

const props = defineProps<{
  /** L'appelant gère la collection : 👍 l'ajoute aux réponses validées. */
  gestionnaire?: boolean
  message: ChatMessage & { vote?: 'up' | 'down' | null }
  /** Le titre du repli de la trace ; par défaut celui du bac à sable d'une collection. */
  titreTrace?: string
  /** Pas de barre d'avis (aucune route ne recueille encore l'avis sur un assistant). */
  sansAvis?: boolean
  /** La réponse est une réponse fiable servie telle quelle : badge, et pas d'alerte « aucune source ». */
  reponseFiable?: boolean
  /** Réponse rédigée d'un assistant : les numéros des passages cités. Leurs puces portent le numéro du
   *  renvoi ; les autres passages se replient à part. Absent : une puce par fichier, sans tri. */
  cites?: number[]
}>()

const emit = defineEmits<{
  (e: 'vote', value: 'up' | 'down'): void
}>()

/** Dedupe sources by filename so 5 chunks from the same PDF show once. */
function dedupliquer (sources: any[]): any[] {
  const seen = new Set<string>()
  const out: any[] = []
  for (const s of sources) {
    const k = s.original_filename || s.filename || JSON.stringify(s).slice(0, 40)
    if (seen.has(k)) {
      continue
    }
    seen.add(k)
    out.push(s)
  }
  return out
}
const deduped = computed(() => dedupliquer(props.message.sources || []))

/** Les passages cités, dans l'ordre de leurs renvois, puis les autres (un par fichier). */
const pucesCitees = computed(() => (props.cites || [])
  .map(n => ({ n, source: props.message.sources?.[n - 1] }))
  .filter(p => p.source))
const autresPuces = computed(() => {
  const cites = new Set(props.cites || [])
  return dedupliquer((props.message.sources || []).filter((_, i) => !cites.has(i + 1)))
})

const rendered = computed(() => renderMarkdownSafe(props.message.content))

/** Un renvoi `[n]` d'une réponse rédigée (lien `data-citation`) ouvre le passage n dans la fenêtre de lecture. */
const citation = ref<Record<string, any> | null>(null)
function surClicReponse (ev: MouseEvent) {
  const n = numeroCitation(ev)
  const source = n ? props.message.sources?.[n - 1] : undefined
  if (source) {
    ev.preventDefault()
    citation.value = source
  }
}

function onVote (v: 'up' | 'down') {
  emit('vote', v)
}
</script>

<template>
  <div
    class="myrag-msg"
    :class="`myrag-msg--${message.role}`"
  >
    <div class="myrag-msg__role">
      {{ message.role === 'user' ? 'Vous' : '🤖 Assistant' }}
    </div>
    <p
      v-if="reponseFiable && message.role === 'assistant'"
      class="fr-mb-1v"
    >
      <span class="fr-badge fr-badge--sm fr-badge--success fr-badge--no-icon">Réponse fiable</span>
    </p>
    <div
      v-if="message.role === 'user'"
      class="myrag-msg__body"
    >
      {{ message.content }}
    </div>
    <div
      v-else
      class="myrag-msg__body myrag-md"
      @click="surClicReponse"
      v-html="rendered"
    />
    <PlaygroundLecteurCitation
      v-if="message.role === 'assistant'"
      :source="citation"
      @close="citation = null"
    />

    <!-- Source chips inline under the assistant reply -->
    <div
      v-if="message.role === 'assistant' && (cites ? pucesCitees.length : message.sources?.length)"
      class="myrag-msg__sources"
    >
      <template v-if="cites">
        <span
          v-for="p in pucesCitees"
          :key="p.n"
          class="myrag-msg__citee"
        >
          <span class="myrag-msg__numero">[{{ p.n }}]</span>
          <PlaygroundSourceChip :source="p.source!" />
        </span>
      </template>
      <template v-else>
        <PlaygroundSourceChip
          v-for="(s, i) in deduped"
          :key="i"
          :source="s"
        />
      </template>
    </div>
    <details
      v-if="message.role === 'assistant' && cites && autresPuces.length"
      class="myrag-msg__autres fr-text--sm"
    >
      <summary>
        {{ pucesCitees.length ? 'Autres passages trouvés, non cités' : 'Passages trouvés, non retenus pour la réponse' }}
        ({{ autresPuces.length }})
      </summary>
      <div class="myrag-msg__sources">
        <PlaygroundSourceChip
          v-for="(s, i) in autresPuces"
          :key="i"
          :source="s"
        />
      </div>
    </details>

    <!-- L'invitation à mettre à jour un index Résana ancien ou incomplet (pour qui le peut). -->
    <div
      v-for="a in message.role === 'assistant' ? (message.avis || []) : []"
      :key="a.code + a.collection"
      class="fr-notice fr-notice--info fr-mt-1w myrag-msg__avis"
    >
      <div class="fr-container">
        <div class="fr-notice__body">
          <p class="fr-notice__title fr-text--sm">
            {{ a.message }}
            <NuxtLink
              :to="a.action.url"
              class="fr-link fr-ml-1w"
            >
              {{ a.action.libelle }}
            </NuxtLink>
          </p>
        </div>
      </div>
    </div>

    <!-- No-source warning when RAG returned nothing -->
    <p
      v-if="message.role === 'assistant' && !reponseFiable && !message.error && !message.sources?.length && message.content"
      class="fr-text--xs"
      style="color:#b34000;margin-top:0.4rem;"
    >
      Aucune source retrouvée — la recherche n'a trouvé aucun passage pertinent dans les documents de la collection.
    </p>

    <!-- Debug accordion & vote bar only on assistant turns -->
    <template v-if="message.role === 'assistant' && !message.error">
      <PlaygroundDebugAccordion
        :model="message.model"
        :sources="message.sources"
        :fallback-used="message.fallbackUsed"
        :titre="titreTrace"
      >
        <!-- Ce que la page ajoute à la trace (le plan suivi par un assistant). -->
        <template
          v-if="$slots.trace"
          #complement
        >
          <slot name="trace" />
        </template>
      </PlaygroundDebugAccordion>
      <PlaygroundVoteBar
        v-if="!sansAvis"
        :vote="message.vote ?? null"
        :disabled="!!message.vote"
        :gestionnaire="gestionnaire"
        @vote="onVote"
      />
    </template>
  </div>
</template>

<style scoped>
.myrag-msg {
  padding: 0.8rem 1rem;
  border-radius: 6px;
  margin-bottom: 1rem;
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
  word-break: break-word;
}
.myrag-msg__sources {
  margin-top: 0.6rem;
  display: flex;
  flex-wrap: wrap;
}
.myrag-msg__citee { display: inline-flex; align-items: center; }
.myrag-msg__numero { font-size: 0.75rem; font-weight: 700; margin-right: 0.15rem; color: var(--text-action-high-blue-france); }
.myrag-msg__autres { margin-top: 0.5rem; }
.myrag-msg__autres summary { cursor: pointer; color: var(--text-mention-grey); }
.myrag-md :deep(p:first-child) { margin-top: 0; }
.myrag-md :deep(p:last-child) { margin-bottom: 0; }
.myrag-md :deep(ul),
.myrag-md :deep(ol) { padding-left: 1.2rem; margin: 0.4rem 0; }
.myrag-md :deep(code) {
  background: #e8e8e8;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 0.85em;
}
.myrag-md :deep(pre) {
  background: #282c34;
  color: #f0f0f0;
  padding: 0.6rem 0.8rem;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 0.82em;
}
.myrag-md :deep(pre code) { background: transparent; padding: 0; }
.myrag-md :deep(a.assistant-citation) { font-size: 0.8em; vertical-align: super; text-decoration: none; }
</style>
