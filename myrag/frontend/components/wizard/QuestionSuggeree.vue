<script setup lang="ts">
/**
 * Une question à essayer, à droite de l'étape 4 : son texte, « Poser » (ou « Reposer »), et où
 * elle en est : rien, répond / ne répond pas (verdict technique), validée / insuffisante (avis).
 */
import type { Validation, VerdictTechnique } from '~/utils/wizard'

defineProps<{
  texte: string
  verdict?: VerdictTechnique | null
  validation?: Validation
  posee?: boolean
  loading?: boolean
}>()
const emit = defineEmits<{ poser: [] }>()
</script>

<template>
  <div
    class="suggeree"
    :class="{ 'suggeree--posee': posee }"
  >
    <p class="fr-text--sm fr-mb-1w">
      {{ texte }}
    </p>
    <div class="suggeree__pied">
      <button
        type="button"
        class="fr-btn fr-btn--sm"
        :class="posee ? 'fr-btn--tertiary' : 'fr-btn--secondary'"
        :disabled="loading"
        @click="emit('poser')"
      >
        {{ posee ? '↻ Reposer' : '▶ Poser' }}
      </button>
      <span
        v-if="validation === 'oui'"
        class="fr-badge fr-badge--sm fr-badge--success fr-badge--no-icon"
      >✓ Validée</span>
      <span
        v-else-if="validation === 'non'"
        class="fr-badge fr-badge--sm fr-badge--warning fr-badge--no-icon"
      >✗ Insuffisante</span>
      <span
        v-else-if="verdict"
        class="fr-badge fr-badge--sm fr-badge--no-icon"
        :class="verdict.cle === 'repond' ? 'fr-badge--info' : 'fr-badge--warning'"
      >{{ verdict.cle === 'repond' ? 'Répond' : 'Ne répond pas' }}</span>
    </div>
  </div>
</template>

<style scoped>
.suggeree { background: #fff; border: 1px solid var(--border-default-grey); border-left: 3px solid var(--border-default-grey); padding: .6rem .75rem; margin-bottom: .6rem; }
.suggeree--posee { border-left-color: var(--border-active-blue-france); }
.suggeree__pied { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
</style>
