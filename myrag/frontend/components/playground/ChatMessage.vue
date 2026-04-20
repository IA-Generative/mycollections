<template>
  <div class="myrag-msg" :class="`myrag-msg--${message.role}`">
    <div class="myrag-msg__role">
      {{ message.role === 'user' ? 'Vous' : '🤖 Assistant' }}
    </div>
    <div v-if="message.role === 'user'" class="myrag-msg__body">{{ message.content }}</div>
    <div v-else class="myrag-msg__body myrag-md" v-html="rendered"></div>

    <!-- Source chips inline under the assistant reply -->
    <div v-if="message.role === 'assistant' && message.sources?.length" class="myrag-msg__sources">
      <PlaygroundSourceChip v-for="(s, i) in deduped" :key="i" :source="s" />
    </div>

    <!-- No-source warning when RAG returned nothing -->
    <p v-if="message.role === 'assistant' && !message.error && !message.sources?.length && message.content"
       class="fr-text--xs" style="color:#b34000;margin-top:0.4rem;">
      Aucune source retrouvee — le RAG n'a pas trouve de chunks pertinents.
    </p>

    <!-- Debug accordion & vote bar only on assistant turns -->
    <template v-if="message.role === 'assistant' && !message.error">
      <PlaygroundDebugAccordion :model="message.model" :sources="message.sources" :fallback-used="message.fallbackUsed" />
      <PlaygroundVoteBar :vote="message.vote ?? null" :disabled="!!message.vote" @vote="onVote" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { marked } from 'marked'
import type { ChatMessage } from '~/composables/useChat'

const props = defineProps<{
  message: ChatMessage & { vote?: 'up' | 'down' | null }
}>()

const emit = defineEmits<{
  (e: 'vote', value: 'up' | 'down'): void
}>()

/** Dedupe sources by filename so 5 chunks from the same PDF show once. */
const deduped = computed(() => {
  const seen = new Set<string>()
  const out: any[] = []
  for (const s of props.message.sources || []) {
    const k = s.original_filename || s.filename || JSON.stringify(s).slice(0, 40)
    if (seen.has(k)) continue
    seen.add(k)
    out.push(s)
  }
  return out
})

const rendered = computed(() => {
  if (!props.message.content) return ''
  return marked.parse(props.message.content, { breaks: true }) as string
})

function onVote(v: 'up' | 'down') {
  emit('vote', v)
}
</script>

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
</style>
