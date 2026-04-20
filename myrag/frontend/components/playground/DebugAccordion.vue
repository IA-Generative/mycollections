<template>
  <details v-if="model || (sources && sources.length)" class="myrag-debug">
    <summary class="myrag-debug__summary">
      Voir comment cette reponse a ete construite
    </summary>
    <div class="myrag-debug__body">
      <p class="fr-text--xs" style="margin:0.3rem 0;">
        <strong>Modele :</strong> {{ model || '—' }}
        <span v-if="fallbackUsed" style="color:#b34000;"> — fallback (pas de chunks RAG)</span>
      </p>
      <p v-if="sources?.length" class="fr-text--xs" style="margin:0.3rem 0;">
        <strong>{{ sources.length }} source(s) retrouvee(s)</strong> — chunks bruts injectes au LLM :
      </p>
      <div v-for="(chunk, i) in sources" :key="i" class="myrag-debug__chunk">
        <div class="myrag-debug__chunk-header">
          {{ prettyName(chunk.original_filename || chunk.filename || '') || `Source ${i + 1}` }}
          <span v-if="chunk.page" style="color:#666;font-weight:normal;"> · p. {{ chunk.page }}</span>
        </div>
        <div class="myrag-debug__chunk-body">{{ truncate(chunk.content) }}</div>
      </div>
    </div>
  </details>
</template>

<script setup lang="ts">
import { prettyName } from '~/utils/playground'

defineProps<{
  model?: string
  sources?: any[]
  fallbackUsed?: boolean
}>()

function truncate(s: string | undefined): string {
  if (!s) return '(pas de contenu)'
  return s.length > 400 ? s.substring(0, 400) + '…' : s
}
</script>

<style scoped>
.myrag-debug {
  margin-top: 0.6rem;
  font-size: 0.85rem;
}
.myrag-debug__summary {
  cursor: pointer;
  color: #666;
  padding: 0.2rem 0;
  user-select: none;
}
.myrag-debug__summary:hover { color: #000091; }
.myrag-debug__body { padding: 0.5rem 0.8rem; background: #f6f6f6; border-left: 2px solid #dddddd; margin-top: 0.4rem; }
.myrag-debug__chunk { margin: 0.4rem 0; padding-bottom: 0.4rem; border-bottom: 1px dashed #ddd; }
.myrag-debug__chunk:last-child { border-bottom: none; }
.myrag-debug__chunk-header { font-weight: 600; font-size: 0.82rem; }
.myrag-debug__chunk-body { white-space: pre-wrap; font-size: 0.78rem; color: #444; margin-top: 0.2rem; }
</style>
