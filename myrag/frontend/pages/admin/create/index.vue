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
    chapeau="Rassemblez vos documents pour que vos collègues puissent les interroger en langage courant. Vous n'avez rien à préparer : l'assistant découpe, indexe et vérifie pour vous."
  >
    <template #formulaire>
      <h2 class="fr-h4">
        Avant de créer une collection
      </h2>
      <div class="fr-callout fr-mb-6w">
        <h3 class="fr-callout__title fr-h6">
          Au préalable
        </h3>
        <ul class="fr-callout__text fr-text--md">
          <li>
            <strong>Elle n'existe pas déjà :</strong> une collection proche, peut-être plus large, est-elle déjà dans le
            <NuxtLink
              to="/admin/catalog"
              class="fr-link"
            >
              catalogue
            </NuxtLink> ? Contactez son responsable plutôt que de la dupliquer.
          </li>
          <li><strong>Elle servira à d'autres :</strong> vos collègues ont-ils les mêmes questions récurrentes que vous ? Une collection utile est une collection interrogée.</li>
          <li><strong>Vous pouvez la tenir à jour :</strong> qui remplacera les documents quand ils changeront ?</li>
        </ul>
      </div>

      <fieldset
        class="fr-fieldset"
        aria-labelledby="titre-sources"
      >
        <legend
          id="titre-sources"
          class="fr-fieldset__legend"
        >
          <h2 class="fr-h4 fr-mb-0">
            D'où viennent vos documents ?
          </h2>
        </legend>
        <div
          v-for="s in cartes"
          :key="s.cle"
          class="fr-fieldset__element fr-fieldset__element--inline source"
        >
          <div class="fr-radio-group fr-radio-rich">
            <input
              :id="`source-${s.cle}`"
              v-model="selected"
              type="radio"
              name="source"
              :value="s.cle"
            >
            <label
              class="fr-label"
              :for="`source-${s.cle}`"
            >
              {{ s.nom }}
              <span class="fr-hint-text">{{ s.description }}</span>
            </label>
            <div class="fr-radio-rich__img">
              <span
                class="fr-icon--lg"
                :class="[s.icone]"
                aria-hidden="true"
              />
            </div>
          </div>
        </div>
      </fieldset>
      <p
        v-if="bientot"
        class="fr-text--sm source__bientot"
      >
        {{ bientot }}
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
.source { flex: 1 1 18rem; }
.source__bientot { color: var(--text-mention-grey); }
</style>
