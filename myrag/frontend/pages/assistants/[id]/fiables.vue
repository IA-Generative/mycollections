<script setup lang="ts">
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
const id = useRoute().params.id as string
useHead({ title: `Réponses fiables — ${id} — Mes collections` })
</script>

<template>
  <AssistantsCadre
    :id="id"
    rubrique="Réponses fiables"
  >
    <template #default="{ donnees }">
      <AssistantsFiables
        :id="id"
        :seuil="donnees.fiche.seuil_fiable"
      />
    </template>
  </AssistantsCadre>
</template>
