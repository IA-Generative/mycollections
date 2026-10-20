<script setup lang="ts">
import type { FicheAssistant, ResultatAssistant } from '~/utils/assistants'
import { sourceDuPassage, traceDuPlan } from '~/utils/assistants'
import { renderMarkdownSafe } from '~/utils/sanitize'

/**
 * Ce qu'a rendu l'assistant pour une question : la réponse (Markdown assaini), ses passages (puces
 * de source, fenêtre de lecture) et le plan suivi. Sert le bouton « Tester » des consignes.
 */
const props = defineProps<{
  resultat: ResultatAssistant
  fiche: Pick<FicheAssistant, 'sources' | 'consignes'> | null
  titre: (id: string) => string
}>()

const trace = computed(() => traceDuPlan(props.resultat.plan, props.fiche, props.titre, props.resultat))
const reponse = computed(() => props.resultat.reponse ? renderMarkdownSafe(props.resultat.reponse) : '')
const sources = computed(() => props.resultat.passages.map(p => sourceDuPassage(p, props.titre)))
</script>

<template>
  <div class="assistant-resultat">
    <h3 class="fr-h6 fr-mb-1w">
      Réponse
      <span
        v-if="resultat.plan.reponse_fiable"
        class="fr-badge fr-badge--sm fr-badge--success fr-badge--no-icon fr-ml-1w"
      >Réponse fiable</span>
    </h3>
    <!-- eslint-disable-next-line vue/no-v-html -- Markdown assaini par renderMarkdownSafe -->
    <div
      v-if="reponse"
      class="fr-text--sm assistant-resultat__reponse"
      v-html="reponse"
    />
    <p
      v-else
      class="fr-text--sm"
    >
      L'assistant a rendu les passages ci-dessous, sans rédiger de réponse.
    </p>
    <p
      v-if="resultat.plan.reponse_fiable"
      class="fr-text--sm"
    >
      Une réponse déjà vérifiée a été servie telle quelle : aucun passage n'a été cherché.
    </p>
    <div
      v-if="sources.length"
      class="assistant-resultat__sources"
    >
      <PlaygroundSourceChip
        v-for="(s, i) in sources"
        :key="i"
        :source="s"
      />
    </div>
    <p
      v-else-if="!resultat.plan.reponse_fiable"
      class="fr-text--sm"
    >
      Aucun passage trouvé.
    </p>
    <h3 class="fr-h6 fr-mt-2w fr-mb-1w">
      Comment l'assistant a cherché
    </h3>
    <AssistantsTrace :trace="trace" />
  </div>
</template>

<style scoped>
.assistant-resultat { padding: 1rem; background: var(--background-alt-grey); }
.assistant-resultat__reponse :deep(p:last-child) { margin-bottom: 0; }
.assistant-resultat__sources { display: flex; flex-wrap: wrap; }
</style>
