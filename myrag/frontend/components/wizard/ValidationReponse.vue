<script setup lang="ts">
/**
 * Sous une réponse de l'étape 4 : le verdict technique (la collection a-t-elle trouvé et répondu ?)
 * et l'avis de la personne, qui seule sait si la réponse est bonne. L'avis se donne une fois.
 */
import type { Validation, VerdictTechnique } from '~/utils/wizard'

defineProps<{
  verdict: VerdictTechnique | null
  validation: Validation
  enCours?: boolean
  erreur?: string
}>()
const emit = defineEmits<{ valider: [v: 'oui' | 'non'] }>()
</script>

<template>
  <div
    class="validation"
    aria-live="polite"
  >
    <p
      v-if="verdict"
      class="fr-badge fr-badge--sm fr-mb-1w"
      :class="verdict.cle === 'repond' ? 'fr-badge--success' : 'fr-badge--warning'"
    >
      {{ verdict.libelle }}
    </p>
    <p
      v-if="verdict?.aide"
      class="fr-text--xs fr-mb-1w validation__aide"
    >
      {{ verdict.aide }}
    </p>
    <div
      v-if="validation"
      class="fr-text--sm validation__note"
    >
      <span
        class="fr-icon-check-line fr-icon--sm"
        aria-hidden="true"
      />
      {{ validation === 'oui' ? 'Noté : la réponse vous convient. Elle rejoint les réponses validées de la collection.' : 'Noté : réponse insuffisante. La question reste à relire dans la page Qualité.' }}
    </div>
    <div
      v-else
      class="validation__choix"
    >
      <span class="fr-text--sm">D'après vous, est-ce que ça répond ?</span>
      <ul class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mb-0">
        <li>
          <button
            type="button"
            class="fr-btn fr-btn--sm fr-btn--secondary fr-icon-thumb-up-line fr-btn--icon-left"
            :disabled="enCours"
            @click="emit('valider', 'oui')"
          >
            Oui, ça répond
          </button>
        </li>
        <li>
          <button
            type="button"
            class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-thumb-down-line fr-btn--icon-left"
            :disabled="enCours"
            @click="emit('valider', 'non')"
          >
            Non
          </button>
        </li>
      </ul>
    </div>
    <p
      v-if="erreur"
      class="fr-text--xs fr-mb-0 validation__aide"
    >
      {{ erreur }}
    </p>
  </div>
</template>

<style scoped>
.validation { margin: -.5rem 0 1rem 1rem; padding-left: 1rem; border-left: 2px solid var(--border-default-grey); }
.validation__aide { color: var(--text-mention-grey); }
.validation__choix { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1rem; }
.validation__note { color: var(--text-default-success); }
</style>
