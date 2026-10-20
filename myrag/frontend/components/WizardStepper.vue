<script setup lang="ts">
import { ETAPES_ASSISTANT, etapeSuivante } from '~/utils/wizard'

/** Le stepper DSFR de l'assistant de création : « Étape n sur 5 », le libellé de l'étape, la jauge
 *  et « Étape suivante : … ». Les libellés viennent de utils/wizard.ts (testés). */
const props = defineProps<{ currentStep: number }>()
const libelle = computed(() => ETAPES_ASSISTANT[props.currentStep - 1] || '')
const suivante = computed(() => etapeSuivante(props.currentStep))
</script>

<template>
  <div class="fr-stepper">
    <!-- Un paragraphe et non un titre : le titre de la page (h1) suit, et la hiérarchie reste juste. -->
    <p class="fr-stepper__title">
      {{ libelle }}
      <span class="fr-stepper__state">Étape {{ currentStep }} sur {{ ETAPES_ASSISTANT.length }}</span>
    </p>
    <div
      class="fr-stepper__steps"
      :data-fr-current-step="currentStep"
      :data-fr-steps="ETAPES_ASSISTANT.length"
    />
    <p
      v-if="suivante"
      class="fr-stepper__details"
    >
      <span class="fr-text--bold">Étape suivante :</span> {{ suivante }}
    </p>
  </div>
</template>
