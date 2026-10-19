<script setup lang="ts">
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const id = useRoute().params.id as string
useHead({ title: `Bac à sable — ${id} — Mes collections` })
</script>

<template>
  <AssistantsCadre
    :id="id"
    rubrique="Bac à sable"
  />
</template>
