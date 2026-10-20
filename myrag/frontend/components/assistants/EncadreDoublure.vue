<script setup lang="ts">
import { MESSAGE_DOUBLURE } from '~/utils/assistants'
</script>

<template>
  <!-- La réponse vient de la doublure du moteur (installation de démonstration) : un exemple, pas une vraie recherche. -->
  <div
    class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w"
    role="status"
  >
    <p>{{ MESSAGE_DOUBLURE }}</p>
  </div>
</template>
