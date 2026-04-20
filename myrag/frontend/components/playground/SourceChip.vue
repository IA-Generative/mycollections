<template>
  <span class="myrag-source-chip-wrap"
        @mouseenter="showPreview = true"
        @mouseleave="showPreview = false">
    <a v-if="href"
       :href="href" target="_blank" rel="noopener"
       class="fr-tag fr-tag--sm myrag-source-chip"
       :title="fullName">
      <span class="fr-icon-file-line" aria-hidden="true" style="margin-right:0.3rem;"></span>
      {{ label }}<span v-if="page" class="myrag-source-chip__page">&nbsp;·&nbsp;p. {{ page }}</span>
    </a>
    <span v-else class="fr-tag fr-tag--sm" :title="fullName">
      {{ label }}<span v-if="page">&nbsp;·&nbsp;p. {{ page }}</span>
    </span>

    <!-- Hover preview: tail of the chunk text with a hint to open the full
         view. We already have chunk.content from the /chat payload, so no
         extra fetch is needed. -->
    <span v-if="showPreview && previewText" class="myrag-source-chip__popover" role="tooltip">
      <span class="myrag-source-chip__popover-title">{{ fullName || 'Extrait' }}</span>
      <span class="myrag-source-chip__popover-body">{{ previewText }}</span>
      <span v-if="href" class="myrag-source-chip__popover-hint">Clique pour la vue complete &rarr;</span>
    </span>
  </span>
</template>

<script setup lang="ts">
import { prettyName, proxiedSourceUrl } from '~/utils/playground'

const props = defineProps<{
  source: {
    original_filename?: string
    filename?: string
    file_url?: string
    chunk_url?: string
    page?: number | string
    content?: string
  }
}>()

const showPreview = ref(false)
const fullName = computed(() => props.source.original_filename || props.source.filename || '')
const label = computed(() => prettyName(fullName.value) || 'Source')
const page = computed(() => props.source.page)
const href = computed(() => proxiedSourceUrl(props.source.chunk_url || props.source.file_url))

/** Preview uses the chunk content already embedded in the RAG response;
 *  500 chars is enough to judge relevance without dominating the screen. */
const previewText = computed(() => {
  const raw = (props.source.content || '').trim()
  if (!raw) return ''
  return raw.length > 500 ? raw.substring(0, 500) + '…' : raw
})
</script>

<style scoped>
.myrag-source-chip-wrap {
  position: relative;
  display: inline-block;
}
.myrag-source-chip {
  text-decoration: none;
  margin: 0 0.3rem 0.3rem 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.myrag-source-chip:hover { background: #eceae3; }
.myrag-source-chip__page { color: #666; font-size: 0.85em; }

.myrag-source-chip__popover {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  width: 420px;
  max-width: 70vw;
  padding: 0.7rem 0.9rem;
  background: #fff;
  border: 1px solid #dddddd;
  border-radius: 4px;
  box-shadow: 0 6px 16px rgba(22, 22, 22, 0.12);
  white-space: normal;
  pointer-events: none;
  font-size: 0.82rem;
  line-height: 1.4;
  color: #161616;
}
.myrag-source-chip__popover-title {
  font-weight: 600;
  font-size: 0.78rem;
  color: #3a3a3a;
  word-break: break-word;
}
.myrag-source-chip__popover-body {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow: hidden;
  mask-image: linear-gradient(to bottom, rgba(0,0,0,1) 70%, rgba(0,0,0,0) 100%);
  -webkit-mask-image: linear-gradient(to bottom, rgba(0,0,0,1) 70%, rgba(0,0,0,0) 100%);
}
.myrag-source-chip__popover-hint {
  font-size: 0.72rem;
  color: #000091;
  margin-top: 0.2rem;
}
</style>
