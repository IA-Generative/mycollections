<script setup lang="ts">
/** La fiche d'un assistant s'ouvre sur ses sources. */
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const id = useRoute().params.id as string
await navigateTo(`/assistants/${encodeURIComponent(id)}/sources`, { replace: true })
</script>

<template>
  <div />
</template>
