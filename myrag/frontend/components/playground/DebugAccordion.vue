<template>
  <details v-if="model || (sources && sources.length)" class="myrag-debug">
    <summary class="myrag-debug__summary">
      Voir comment cette réponse a été construite
    </summary>
    <div class="myrag-debug__body">
      <p class="fr-text--xs" style="margin:0.3rem 0;">
        <strong>Modèle :</strong> {{ model || '—' }}
        <span v-if="fallbackUsed" style="color:#b34000;"> — réponse de secours : la recherche habituelle n'a trouvé aucun passage</span>
      </p>
      <p v-if="sources?.length" class="fr-text--xs" style="margin:0.3rem 0;">
        <strong>{{ sources.length }} source(s) retrouvée(s)</strong> — extraits injectés au modèle :
      </p>
      <div v-for="(chunk, i) in sources" :key="i" class="myrag-debug__chunk">
        <div class="myrag-debug__chunk-header">
          {{ chunk.libelle || prettyName(chunk.original_filename || chunk.filename || '') || `Source ${i + 1}` }}
          <span v-if="chunk.page" style="color:#666;font-weight:normal;"> · p. {{ chunk.page }}</span>
        </div>
        <div class="myrag-debug__chunk-body myrag-md" v-html="rendu(chunk.content)"></div>
      </div>
    </div>
  </details>
</template>

<script setup lang="ts">
import { prettyName } from '~/utils/playground'
import { renderMarkdownSafe } from '~/utils/sanitize'

defineProps<{
  model?: string
  sources?: any[]
  fallbackUsed?: boolean
}>()

/** Le morceau est du Markdown (titres, gras, listes) : on le rend en entier, assaini,
 *  dans un cadre à hauteur bornée plutôt que de le couper au milieu d'une balise. */
function rendu(s: string | undefined): string {
  return renderMarkdownSafe(s) || '<p><em>(pas de contenu)</em></p>'
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
.myrag-debug__chunk-body { font-size: 0.78rem; color: #444; margin-top: 0.2rem; max-height: 14rem; overflow-y: auto; }
.myrag-debug__chunk-body :deep(p) { margin: 0 0 0.4rem; font-size: inherit; }
.myrag-debug__chunk-body :deep(p:last-child) { margin-bottom: 0; }
.myrag-debug__chunk-body :deep(h1),
.myrag-debug__chunk-body :deep(h2),
.myrag-debug__chunk-body :deep(h3),
.myrag-debug__chunk-body :deep(h4) { font-size: 0.85rem; margin: 0.4rem 0 0.2rem; }
.myrag-debug__chunk-body :deep(ul),
.myrag-debug__chunk-body :deep(ol) { padding-left: 1.2rem; margin: 0.2rem 0; }
.myrag-debug__chunk-body :deep(li) { font-size: inherit; }
</style>
