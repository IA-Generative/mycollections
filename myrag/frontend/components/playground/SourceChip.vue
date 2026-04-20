<template>
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
</template>

<script setup lang="ts">
import { prettyName, toHttps } from '~/utils/playground'

const props = defineProps<{
  source: {
    original_filename?: string
    filename?: string
    file_url?: string
    chunk_url?: string
    page?: number | string
  }
}>()

const fullName = computed(() => props.source.original_filename || props.source.filename || '')
const label = computed(() => prettyName(fullName.value) || 'Source')
const page = computed(() => props.source.page)
const href = computed(() => toHttps(props.source.chunk_url || props.source.file_url))
</script>

<style scoped>
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
</style>
