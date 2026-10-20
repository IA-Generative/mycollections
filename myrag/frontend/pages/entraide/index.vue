<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { messageErreur } from '~/utils/collectif'
import { adresseAppel, compteReponses, LIBELLES_ETAT_APPEL, LIBELLES_TYPE } from '~/utils/entraide'

definePageMeta({ middleware: 'capacite', capacite: 'entraide' })
useHead({ title: 'Entraide — Mes collections' })

const { listerAppels } = useEntraide()
const { capacites } = useCapacites()
const appels = ref<any[] | null>(null)
const erreur = ref('')
const type = ref('tous')
const recherche = ref('')

const affiches = computed(() => (appels.value || []).filter(a => type.value === 'tous' || a.type === type.value))
const types = ['tous', 'donnee', 'cherche', 'propose']

async function recharger () {
  erreur.value = ''
  try {
    appels.value = (await listerAppels(recherche.value.trim() ? { q: recherche.value.trim() } : undefined)).appels
  }
  catch (e) {
    appels.value = []
    erreur.value = messageErreur(e)
  }
}
onMounted(recharger)
</script>

<template>
  <div>
    <h1 class="fr-h2">
      Entraide
    </h1>
    <p class="fr-text--lead">
      Lancez un appel : le réseau vous montre d'abord ce qui existe déjà, puis des collègues qui peuvent vous aider.
    </p>

    <ul class="fr-btns-group fr-btns-group--inline-md fr-btns-group--icon-left fr-mb-3w">
      <li>
        <NuxtLink
          class="fr-btn fr-icon-add-line fr-btn--icon-left"
          to="/entraide/nouveau"
        >
          Lancer un appel
        </NuxtLink>
      </li>
      <li v-if="capacites.demandes">
        <NuxtLink
          class="fr-btn fr-btn--secondary fr-icon-database-line fr-btn--icon-left"
          to="/demandes?deposer=1"
        >
          Demander une donnée
        </NuxtLink>
      </li>
    </ul>

    <form
      class="fr-search-bar fr-mb-2w"
      role="search"
      @submit.prevent="recharger"
    >
      <label
        class="fr-label"
        for="entraide-recherche"
      >Chercher un appel</label>
      <input
        id="entraide-recherche"
        v-model="recherche"
        class="fr-input"
        type="search"
        placeholder="Chercher un appel"
      >
      <button
        class="fr-btn"
        type="submit"
        title="Chercher"
      >
        Chercher
      </button>
    </form>

    <fieldset class="fr-fieldset fr-mb-2w">
      <legend class="fr-fieldset__legend">
        Types d'appel
      </legend>
      <div
        v-for="t in types"
        :key="t"
        class="fr-fieldset__element fr-fieldset__element--inline"
      >
        <div class="fr-radio-group fr-radio-group--sm">
          <input
            :id="`type-${t}`"
            v-model="type"
            type="radio"
            name="type-appel"
            :value="t"
          >
          <label
            class="fr-label"
            :for="`type-${t}`"
          >{{ t === 'tous' ? 'Tous' : LIBELLES_TYPE[t as keyof typeof LIBELLES_TYPE].libelle }}</label>
        </div>
      </div>
    </fieldset>

    <div
      v-if="erreur"
      class="fr-alert fr-alert--error fr-alert--sm fr-mb-2w"
      role="alert"
    >
      <p>{{ erreur }}</p>
    </div>
    <p v-if="appels === null">
      Chargement…
    </p>
    <p
      v-else-if="affiches.length === 0"
      class="fr-text--sm"
    >
      Aucun appel pour l'instant. Le premier est peut-être le vôtre.
    </p>
    <div
      v-else
      class="fr-grid-row fr-grid-row--gutters"
    >
      <div
        v-for="a in affiches"
        :key="a.id"
        class="fr-col-12 fr-col-md-6"
      >
        <div class="fr-card fr-enlarge-link">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h2 class="fr-card__title">
                <NuxtLink :to="adresseAppel(a)">
                  {{ a.titre }}
                </NuxtLink>
              </h2>
              <p
                v-if="a.texte"
                class="fr-card__desc"
              >
                {{ a.texte.length > 160 ? `${a.texte.slice(0, 160)}…` : a.texte }}
              </p>
              <div class="fr-card__start">
                <ul class="fr-badges-group">
                  <li>
                    <p class="fr-badge fr-badge--sm">
                      {{ LIBELLES_TYPE[a.type as keyof typeof LIBELLES_TYPE]?.libelle || a.type }}
                    </p>
                  </li>
                  <li>
                    <p
                      class="fr-badge fr-badge--sm"
                      :class="LIBELLES_ETAT_APPEL[a.etat]?.badge"
                    >
                      {{ LIBELLES_ETAT_APPEL[a.etat]?.libelle || a.etat }}
                    </p>
                  </li>
                </ul>
              </div>
              <div class="fr-card__end">
                <p class="fr-card__detail">
                  {{ compteReponses(a) }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
