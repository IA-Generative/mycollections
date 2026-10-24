<script setup lang="ts">
import { cartesDeSource, ligneBientot, sourcesSelon } from '~/utils/wizard'

/** Étape 1 de l'assistant de création : avant de créer, puis d'où viennent les documents. Seules
 *  les sources que le code sait traiter sont proposées ; les autres sont annoncées sur une ligne.
 *  Une source gardée par une capacité (Résana) n'est une carte que si elle est allumée. */
const router = useRouter()
const { capacites, charger } = useCapacites()
const sources = computed(() => sourcesSelon(capacites.value))
const cartes = computed(() => cartesDeSource(sources.value))
const bientot = computed(() => ligneBientot(sources.value))
const selected = ref(cartesDeSource()[0]?.cle || '')
onMounted(charger)

function next () {
  // Résana se choisit d'abord dans Résana (espace, dossier, sous-dossiers), la fiche vient après.
  router.push(selected.value === 'resana' ? '/admin/create/resana' : `/admin/create/step-2?source=${selected.value}`)
}
</script>

<template>
  <WizardEtape
    :numero="1"
    titre="Créer une nouvelle collection"
  >
    <template #formulaire>
      <p class="fr-text--lg fr-mb-1w">
        Vos collègues l'interrogeront en langage courant. Rien à préparer.
      </p>
      <!-- Les questions à se poser : repliées, à une ligne, pour que le choix tienne sans défiler. -->
      <details class="avant fr-mb-3v">
        <summary class="fr-text--sm">
          <strong>Avant de commencer</strong> : trois questions à se poser
        </summary>
        <ul class="fr-text--sm fr-mt-1w fr-mb-0">
          <li>
            <strong>Elle n'existe pas déjà :</strong> une collection proche, peut-être plus large, est-elle dans le
            <NuxtLink
              to="/admin/catalog"
              class="fr-link fr-text--sm"
            >
              catalogue
            </NuxtLink> ? Contactez son responsable plutôt que de la dupliquer.
          </li>
          <li><strong>Elle servira à d'autres :</strong> vos collègues ont-ils les mêmes questions récurrentes que vous ?</li>
          <li><strong>Vous pouvez la tenir à jour :</strong> qui remplacera les documents quand ils changeront ?</li>
        </ul>
      </details>

      <fieldset
        class="sources-bloc"
        aria-labelledby="titre-sources"
      >
        <legend
          id="titre-sources"
          class="sources__legende"
        >
          <h2 class="fr-h5 fr-my-0">
            D'où viennent vos documents ?
          </h2>
        </legend>
        <div class="sources">
          <div
            v-for="s in cartes"
            :key="s.cle"
            class="fr-radio-group fr-radio-group--sm tuile"
            :class="{ 'tuile--choisie': selected === s.cle }"
          >
            <input
              :id="`source-${s.cle}`"
              v-model="selected"
              type="radio"
              name="source"
              :value="s.cle"
            >
            <label
              class="fr-label tuile__label"
              :for="`source-${s.cle}`"
            >
              <span class="tuile__nom">{{ s.nom }}</span>
              <span class="fr-hint-text">{{ s.description }}</span>
            </label>
            <span
              class="tuile__icone"
              :class="[s.icone]"
              aria-hidden="true"
            />
          </div>
        </div>
      </fieldset>
      <p
        v-if="bientot"
        class="fr-text--xs fr-mb-0 source__bientot"
      >
        {{ bientot }}
      </p>
      <p class="fr-text--xs fr-mt-1w fr-mb-0 diffusion">
        <strong>Diffusion</strong> : chat MirAI, votre application (API MirAI), MirAI Assistant pour navigateur (un chatbot dans votre
        application) ou ici même. Vous choisirez à l'étape « Partage ».
      </p>
    </template>

    <template #actions>
      <ul class="fr-btns-group fr-btns-group--right fr-btns-group--inline-md">
        <li>
          <NuxtLink
            to="/"
            class="fr-btn fr-btn--tertiary-no-outline"
          >
            Annuler
          </NuxtLink>
        </li>
        <li>
          <button
            type="button"
            class="fr-btn"
            :disabled="!selected"
            @click="next"
          >
            Commencer la création
          </button>
        </li>
      </ul>
    </template>
  </WizardEtape>
</template>

<style scoped>
.avant summary { cursor: pointer; color: var(--text-mention-grey); }
.avant ul { color: var(--text-default-grey); }
/* Les sources en tuiles compactes : trois par ligne sur grand écran, une par ligne sur mobile. */
.sources-bloc { border: 0; padding: 0; margin: 0; min-width: 0; }
.sources__legende { float: left; width: 100%; padding: 0; margin: 0 0 .5rem; }
.sources__legende + * { clear: both; }
.sources { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: .75rem; width: 100%; }
.tuile { position: relative; box-sizing: border-box; width: 100%; max-width: none; margin: 0; padding: .75rem 3rem .75rem .75rem; border: 1px solid var(--border-default-grey); background: var(--background-default-grey); }
.tuile:hover { background: var(--background-default-grey-hover); }
.tuile--choisie { border-color: var(--border-active-blue-france); box-shadow: inset 0 0 0 1px var(--border-active-blue-france); }
.tuile__label { width: 100%; }
.tuile__nom { font-weight: 500; }
.tuile__icone { position: absolute; top: .75rem; right: .75rem; color: var(--text-action-high-blue-france); }
.source__bientot { color: var(--text-mention-grey); margin-top: .5rem; }
.diffusion { color: var(--text-mention-grey); }
</style>
