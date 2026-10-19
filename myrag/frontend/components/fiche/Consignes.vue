<script setup lang="ts">
import { apercuConsignes } from '~/utils/fiche'
import { libelleConsignes } from '~/utils/libelles'

/** « Consignes données à l'assistant » : le modèle, un extrait (texte seulement), et les gestes
 *  pour les modifier (qui gère) ou les tester (tous). */
const props = defineProps<{ id: string, modele?: string, consignes?: string, peutGerer: boolean }>()

const complet = ref(false)
const apercu = computed(() => apercuConsignes(props.consignes))
</script>

<template>
  <section
    id="consignes"
    class="fiche-bloc"
    aria-labelledby="titre-consignes"
    tabindex="-1"
  >
    <h2
      id="titre-consignes"
      class="fr-h5"
    >
      <span
        class="fr-icon-file-text-line fr-mr-1w"
        aria-hidden="true"
      />Consignes données à l'assistant
    </h2>
    <p class="fr-text--sm">
      Modèle <strong>{{ libelleConsignes(modele) }}</strong>. C'est ici que se règlent le ton, les sources à citer et ce que l'assistant doit refuser.
    </p>
    <pre class="fiche-consignes">{{ complet ? consignes : apercu.texte }}</pre>
    <button
      v-if="apercu.tronque"
      type="button"
      class="fr-link fr-text--sm fr-mb-2w"
      :aria-expanded="complet ? 'true' : 'false'"
      @click="complet = !complet"
    >
      {{ complet ? 'Réduire' : 'Lire toutes les consignes' }}
    </button>
    <div class="fiche-bloc__actions">
      <NuxtLink
        v-if="peutGerer"
        :to="`/c/${id}/prompt`"
        class="fr-btn fr-btn--secondary fr-btn--sm"
      >
        Modifier les consignes
      </NuxtLink>
      <NuxtLink
        :to="`/c/${id}/playground`"
        class="fr-link fr-text--sm"
      >
        Tester sur une question
      </NuxtLink>
    </div>
  </section>
</template>
