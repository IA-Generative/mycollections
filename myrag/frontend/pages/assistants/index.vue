<script setup lang="ts">
import { canauxActifs, etatAssistant, resumeSources } from '~/utils/assistants'

/** Les assistants de recherche que je peux voir (B1). Un assistant « miroir » est celui d'une
 *  collection publiée : il ne s'assemble pas, il suit sa collection. */
definePageMeta({ middleware: 'capacite', capacite: 'assistants' })
useHead({ title: 'Assistants de recherche — Mes collections' })

const { lister } = useAssistants()
const assistants = ref<any[]>([])
const charge = ref(false)
const erreur = ref('')
const montrerMiroirs = ref(false)
const assembles = computed(() => assistants.value.filter(a => !a.collection_name))
const miroirs = computed(() => assistants.value.filter(a => a.collection_name))

onMounted(async () => {
  try {
    assistants.value = await lister()
  }
  catch (e) {
    erreur.value = messageErreur(e)
  }
  charge.value = true
})
</script>

<template>
  <div>
    <div class="assistants-tete fr-mb-2w">
      <div>
        <h1 class="fr-h3 fr-mb-0">
          Assistants de recherche
        </h1>
        <p class="fr-text--sm fr-mb-0 assistants-discret">
          Un assistant interroge plusieurs collections à la fois, selon vos consignes, et cite ses sources.
        </p>
      </div>
      <NuxtLink
        to="/assistants/nouveau"
        class="fr-btn fr-btn--sm fr-btn--icon-left fr-icon-add-line"
      >
        Créer un assistant
      </NuxtLink>
    </div>

    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>
    <p
      v-else-if="!charge"
      class="fr-text--sm"
    >
      Chargement…
    </p>
    <div
      v-else-if="!assembles.length"
      class="fr-callout"
    >
      <h2 class="fr-callout__title fr-h6">
        Aucun assistant pour l'instant
      </h2>
      <p class="fr-callout__text fr-text--sm">
        Réunissez plusieurs de vos collections derrière un seul assistant : vos collègues posent une question, il cherche au bon endroit.
      </p>
      <NuxtLink
        to="/assistants/nouveau"
        class="fr-btn fr-btn--sm fr-mt-2w"
      >
        Créer un assistant
      </NuxtLink>
    </div>

    <ul
      v-else
      class="fr-grid-row fr-grid-row--gutters assistants-liste"
      role="list"
    >
      <li
        v-for="a in assembles"
        :key="a.id"
        class="fr-col-12 fr-col-md-6 fr-col-xl-4"
      >
        <article class="assistant-carte">
          <div class="assistant-carte__tete">
            <h2 class="fr-h6 fr-mb-0">
              <NuxtLink
                :to="`/assistants/${a.id}/sources`"
                class="assistant-carte__lien"
              >
                {{ a.titre }}
              </NuxtLink>
            </h2>
            <span
              class="fr-badge fr-badge--sm fr-badge--no-icon"
              :class="etatAssistant(a.version).classe"
            >{{ etatAssistant(a.version).libelle }}</span>
          </div>
          <p
            v-if="a.description"
            class="fr-text--sm fr-mb-0 assistants-discret"
          >
            {{ a.description }}
          </p>
          <p class="fr-text--xs fr-mb-0">
            <span
              class="fr-icon-database-line fr-icon--sm fr-mr-1v"
              aria-hidden="true"
            />{{ resumeSources(a.sources.length, a.sources_masquees) }}
            <template v-if="canauxActifs(a.publication).length">
              · servi dans {{ canauxActifs(a.publication).join(', ') }}
            </template>
          </p>
        </article>
      </li>
    </ul>

    <!-- Les assistants miroirs : un par collection publiée, créés seuls. Repliés : ils sont nombreux. -->
    <section
      v-if="miroirs.length"
      class="fr-mt-4w"
    >
      <button
        type="button"
        class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-btn--icon-left"
        :class="montrerMiroirs ? 'fr-icon-arrow-up-s-line' : 'fr-icon-arrow-down-s-line'"
        :aria-expanded="montrerMiroirs ? 'true' : 'false'"
        aria-controls="assistants-miroirs"
        @click="montrerMiroirs = !montrerMiroirs"
      >
        {{ miroirs.length }} assistant{{ miroirs.length > 1 ? 's' : '' }} d'une seule collection, créé{{ miroirs.length > 1 ? 's' : '' }} à sa publication
      </button>
      <ul
        v-show="montrerMiroirs"
        id="assistants-miroirs"
        class="fr-mt-1w fr-text--sm"
      >
        <li
          v-for="a in miroirs"
          :key="a.id"
        >
          <NuxtLink
            :to="`/c/${a.collection_name}`"
            class="fr-link fr-text--sm"
          >
            {{ a.titre }}
          </NuxtLink>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.assistants-tete { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: .75rem 1.5rem; }
.assistants-discret { color: var(--text-mention-grey); }
.assistants-liste { list-style: none; padding: 0; }
.assistant-carte { height: 100%; display: flex; flex-direction: column; gap: .5rem; padding: 1rem 1.25rem; border: 1px solid var(--border-default-grey); border-bottom: 3px solid var(--border-plain-blue-france); }
.assistant-carte__tete { display: flex; justify-content: space-between; align-items: flex-start; gap: .75rem; }
.assistant-carte__lien { background-image: none; }
.assistant-carte__lien:hover { text-decoration: underline; }
</style>
