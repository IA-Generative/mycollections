<script setup lang="ts">
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const id = useRoute().params.id as string
useHead({ title: `Publication — ${id} — Mes collections` })
</script>

<template>
  <AssistantsCadre
    :id="id"
    rubrique="Publication"
  />
</template>
