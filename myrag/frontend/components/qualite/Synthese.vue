<template>
  <section class="synthese" aria-labelledby="synthese-titre">
    <h2 id="synthese-titre" class="fr-h6 fr-mb-1w">{{ titre || 'Aujourd\'hui' }}</h2>
    <template v-if="m">
      <p class="synthese__score fr-mb-1v">
        <strong>{{ m.score }} %</strong>
        <span class="fr-badge fr-badge--sm fr-badge--no-icon" :class="app.classe">{{ app.libelle }}</span>
      </p>
      <div class="synthese__barre" role="img" :aria-label="`Qualité mesurée : ${m.score} sur 100`">
        <div class="synthese__plein" :class="`synthese__plein--${niveau}`" :style="{ width: `${m.score}%` }" />
      </div>
      <p class="fr-text--sm fr-mt-1w fr-mb-1v">
        {{ conformes }} / {{ m.nb_traitees }} réponses justes · {{ resumeVerdicts(m.verdicts) }}
      </p>
      <p class="fr-text--xs fr-mb-1w synthese__discret">
        Mesurée le {{ dateMesure(m.cree_le) }} ·
        {{ m.methode === 'judge' ? 'comparaison par le juge IA' : 'comparaison par similarité (juge indisponible)' }}
      </p>
    </template>
    <p v-else class="fr-text--sm fr-mb-1w">
      Aucune mesure pour l'instant. Validez quelques questions du jeu, puis mesurez : chaque question est posée
      à la collection et sa réponse comparée à la vôtre.
    </p>
    <p v-if="sat && sat.total" class="fr-text--sm fr-mb-0">
      Satisfaction des usagers : <strong>{{ Math.round(sat.satisfaction_rate * 100) }} %</strong>
      ({{ sat.positive }} 👍 / {{ sat.negative }} 👎)
      <template v-if="sat.pending_review"> · {{ sat.pending_review }} avis à relire</template>
    </p>
    <p v-else class="fr-text--xs fr-mb-0 synthese__discret">Aucun avis d'usager pour l'instant.</p>
  </section>
</template>

<script setup lang="ts">
import { appreciation, dateMesure, resumeVerdicts, type Mesure } from '~/utils/qualite'

/** Le bloc « Aujourd'hui » : la dernière mesure terminée et la satisfaction des usagers. */
const props = defineProps<{ synthese: any, titre?: string }>()
const m = computed<Mesure | null>(() => props.synthese?.derniere_terminee || null)
const sat = computed(() => props.synthese?.satisfaction || null)
const app = computed(() => appreciation(m.value?.score))
const conformes = computed(() => (m.value ? m.value.verdicts.conformes + m.value.verdicts.refus_ok : 0))
const niveau = computed(() => {
  const s = m.value?.score ?? 0
  return s >= 60 ? 'bon' : s >= 40 ? 'moyen' : 'faible'
})
</script>

<style scoped>
.synthese__score { display: flex; align-items: baseline; gap: .75rem; font-size: 1.75rem; line-height: 1.2; }
.synthese__barre { height: .5rem; background: var(--background-contrast-grey); }
.synthese__plein { height: 100%; }
.synthese__plein--bon { background: var(--background-flat-success); }
.synthese__plein--moyen { background: var(--background-flat-warning); }
.synthese__plein--faible { background: var(--background-flat-error); }
.synthese__discret { color: var(--text-mention-grey); }
</style>
