<script setup lang="ts">
/**
 * Le gabarit commun des cinq étapes de l'assistant de création (maquette du 2026-10-19) : stepper, titre, chapeau, formulaire à gauche et encadré à droite,
 * actions en bas à droite (Annuler · Étape précédente · Étape suivante).
 */
defineProps<{
  numero: number
  titre: string
  chapeau?: string
}>()
const slots = useSlots()
</script>

<template>
  <div class="etape">
    <WizardStepper
      :current-step="numero"
      class="etape__stepper"
    />

    <h1 class="fr-h2 fr-mb-1w">
      {{ titre }}
    </h1>
    <p
      v-if="chapeau || slots.chapeau"
      class="fr-text--lead fr-mb-4w etape__chapeau"
    >
      <slot name="chapeau">
        {{ chapeau }}
      </slot>
    </p>

    <div class="fr-grid-row fr-grid-row--gutters">
      <div
        class="fr-col-12"
        :class="{ 'fr-col-lg-8': slots.encadre }"
      >
        <slot name="formulaire" />
      </div>
      <div
        v-if="slots.encadre"
        class="fr-col-12 fr-col-lg-4"
      >
        <div class="fr-callout etape__encadre">
          <slot name="encadre" />
        </div>
      </div>
    </div>

    <div
      v-if="slots.actions"
      class="etape__actions fr-mt-4w"
    >
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.etape__stepper { max-width: 40rem; }
.etape__chapeau { max-width: 48rem; }
.etape__actions { border-top: 1px solid var(--border-default-grey); padding-top: 1.5rem; }
</style>
