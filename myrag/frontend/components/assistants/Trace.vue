<script setup lang="ts">
import type { TracePlan } from '~/utils/assistants'

/**
 * Comment l'assistant a cherché : la consigne retenue, les étapes (source, ce dont chacune part,
 * combien de passages), les sources non interrogées et le compte de celles écartées. Le calcul est
 * dans `traceDuPlan` (utils/assistants.ts, testé) ; ce composant ne fait qu'afficher, sans HTML injecté.
 */
defineProps<{ trace: TracePlan }>()

function pluriel (n: number, mot: string): string {
  return `${n} ${mot}${n > 1 ? 's' : ''}`
}
</script>

<template>
  <div class="assistant-trace">
    <p class="fr-text--sm fr-mb-1w">
      <strong>Où chercher :</strong> {{ trace.methode }}.
      <template v-if="trace.duree">
        Durée : {{ trace.duree }}.
      </template>
    </p>
    <p
      v-if="trace.reponseFiable"
      class="fr-text--sm fr-mb-1w"
    >
      <span class="fr-badge fr-badge--sm fr-badge--success fr-badge--no-icon">Réponse fiable</span>
      Une réponse déjà vérifiée a été servie, sans nouvelle recherche.
    </p>
    <p
      v-if="trace.consigne"
      class="fr-text--sm fr-mb-1w"
    >
      <strong>Consigne retenue :</strong> « {{ trace.consigne.libelle }} »
      <span
        v-if="trace.consigne.score !== null"
        class="assistant-trace__discret"
      >(ressemblance {{ trace.consigne.score }} %)</span>
    </p>
    <p
      v-else-if="!trace.reponseFiable"
      class="fr-text--sm fr-mb-1w"
    >
      Aucune consigne ne s'appliquait : l'assistant a choisi ses sources d'après la question.
    </p>
    <ol
      v-if="trace.etapes.length"
      class="fr-raw-list fr-text--sm fr-mb-1w assistant-trace__etapes"
    >
      <li
        v-for="e in trace.etapes"
        :key="e.n"
      >
        Étape {{ e.n }} : <strong>{{ e.titre }}</strong>
        <span class="assistant-trace__discret"> — {{ pluriel(e.passages, 'passage') }}</span>
        <template v-if="e.apres.length">
          <br><span class="assistant-trace__discret">
            Après {{ e.apres.length > 1 ? 'les étapes' : 'l\'étape' }} {{ e.apres.join(' et ') }}<template v-if="e.avec">, à partir de ce qu'elles ont trouvé (« {{ e.avec }} »)</template>.
          </span>
        </template>
      </li>
    </ol>
    <p
      v-if="trace.nonInterrogees.length"
      class="fr-text--sm fr-mb-1w"
    >
      <strong>Non interrogées :</strong> {{ trace.nonInterrogees.join(', ') }}.
    </p>
    <p
      v-if="trace.ecartees"
      class="fr-text--sm fr-mb-0 assistant-trace__discret"
    >
      {{ pluriel(trace.ecartees, 'source') }} écartée{{ trace.ecartees > 1 ? 's' : '' }} : vous ne pouvez pas {{ trace.ecartees > 1 ? 'les' : 'la' }} lire.
    </p>
  </div>
</template>

<style scoped>
.assistant-trace__discret { color: var(--text-mention-grey); }
.assistant-trace__etapes { margin: 0; padding: 0; }
.assistant-trace__etapes li { margin-bottom: .25rem; }
</style>
