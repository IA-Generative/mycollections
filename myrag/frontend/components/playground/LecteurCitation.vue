<script setup lang="ts">
import { proxiedSourceUrl } from '~/utils/playground'

/**
 * La fenêtre de lecture d'un passage cité par un renvoi `[n]` d'une réponse rédigée : la même que
 * celle d'une puce de source (`SourceChip`), ouverte depuis le texte de la réponse.
 */
const props = defineProps<{
  source: { libelle?: string, titre_document?: string, chunk_url?: string, file_url?: string, page?: number | string, content?: string } | null
}>()
defineEmits<{ (e: 'close'): void }>()

const url = computed(() => proxiedSourceUrl(props.source?.chunk_url || props.source?.file_url))
</script>

<template>
  <PlaygroundSourceViewer
    :open="!!source"
    :url="url"
    :titre="source?.titre_document || source?.libelle || 'Source'"
    :sous-titre="source?.libelle !== source?.titre_document ? source?.libelle : undefined"
    :page="source?.page"
    :contenu-initial="source?.content || ''"
    @close="$emit('close')"
  />
</template>
